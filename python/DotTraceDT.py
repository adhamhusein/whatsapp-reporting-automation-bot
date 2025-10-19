import os
import folium
import rasterio
import numpy as np
import pandas as pd
from PIL import Image
import geopandas as gpd
from datetime import datetime
import matplotlib.pyplot as plt
import io, base64, pyodbc, uuid
from rasterio.plot import reshape_as_image
from rasterio.warp import transform_bounds
from folium.raster_layers import ImageOverlay

class DotTraceDT:
    REGIONS = {
        "PA1": (0.731, 0.691, 117.504, 117.463),
        "PA2": (0.722, 0.676, 117.463, 117.434),
        "PA2-SELATAN": (0.702, 0.682, 117.475, 117.435),
        "PA3-UTARA": (0.674, 0.629, 117.470, 117.422),
        "PA3-SELATAN": (0.608, 0.570, 117.465, 117.425),
    }

    def __init__(self, region: str, tif_path: str, sample_frac: float = 0.2):
        if region not in self.REGIONS:
            raise ValueError(f"Region '{region}' not found in available regions: {list(self.REGIONS.keys())}")
        self.region = region
        self.tif_path = tif_path
        self.sample_frac = sample_frac
        self.df = None
        self.html_file = None
        self.caption = None
        self.analytic_result = None
        self.underspeed_chart = None

    @property
    def bounds(self):
        max_lat, min_lat, max_lon, min_lon = self.REGIONS[self.region]
        return [[min_lat, min_lon], [max_lat, max_lon]]

    @property
    def center(self):
        max_lat, min_lat, max_lon, min_lon = self.REGIONS[self.region]
        return (max_lat + min_lat) / 2, (max_lon + min_lon) / 2

    def query_database(self):
        conn_str = "Driver={SQL Server};Server=LAPTOP-5HOEAIO4\\SQLEXPRESS;Database=db_ewacs_fgdp;Trusted_Connection=yes;"
        sql = """
        select mobileid,reporttime,mobiletypeid,pos_lon,pos_lat
        ,pos_name,pos_speed,mobileactivityid,mobilestatusid,plm_inc
        from db_ewacs_fgdp.dbo.opr_pos
        where reporttime between '2025-06-06 21:00:00' and '2025-06-06 22:00:00'
        and pos_lon>0 and pos_lat>0 and pos_speed between 0 and 60
        """
        with pyodbc.connect(conn_str) as conn:
            df = pd.read_sql(sql, conn)
        if "reporttime" in df.columns:
            df["reporttime"] = df["reporttime"].dt.strftime("%Y-%m-%d %H:%M:%S")
        self.df = df

    def _add_tif(self, m):
        with rasterio.open(self.tif_path) as src:
            img = src.read()
            img_rgb = np.stack([img[0]]*3, axis=0) if img.shape[0] == 1 else img[:3]
            image = reshape_as_image(img_rgb)
            pil_img = Image.fromarray(image)
            buffer = io.BytesIO(); pil_img.save(buffer, format="PNG")
            data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
            if src.crs and src.crs.to_epsg() != 4326:
                minx, miny, maxx, maxy = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            else:
                minx, miny, maxx, maxy = src.bounds
            bounds = [[miny, minx], [maxy, maxx]]
            ImageOverlay(data_url, bounds, opacity=1, zindex=1).add_to(m)

    def _add_trace(self, m):
        max_lat, min_lat, max_lon, min_lon = self.REGIONS[self.region]
        df_r = self.df[(self.df["mobiletypeid"] == 2) &
                       self.df["pos_lon"].between(min_lon, max_lon) &
                       self.df["pos_lat"].between(min_lat, max_lat)]
        sampled = df_r.sample(max(1000, int(len(df_r) * self.sample_frac)), random_state=42)
        gdf = gpd.GeoDataFrame(sampled,
                               geometry=gpd.points_from_xy(sampled.pos_lon, sampled.pos_lat),
                               crs="EPSG:4326")
        folium.Polygon([(max_lat, min_lon), (min_lat, min_lon), (min_lat, max_lon), (max_lat, max_lon)],
                       color="gray").add_to(m)
        folium.GeoJson(
            gdf,
            marker=folium.CircleMarker(),
            style_function=lambda f: {
                "radius": 1,
                "color": self._speed_color(f["properties"]["pos_speed"]),
                "weight": 1,
                "fill": True, "fill_opacity": 1, "opacity": 1
            }
        ).add_to(m)

    def _speed_color(self, s):
        return "blue" if s < 1 else "red" if s < 18 else "yellow" if s < 20 else "green" if s < 25 else "black"

    def _image_to_base64(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string
    
    def analyze_dottrace(self, df):
        df = self.df.copy()
        df["reporttime"] = pd.to_datetime(df["reporttime"])
        duration_hours = (df["reporttime"].max() - df["reporttime"].min()).total_seconds() / 3600
        max_lat, min_lat, max_lon, min_lon = self.REGIONS[self.region]

        mask = (
            ~df["pos_name"].str.startswith(("IN", "FRONT", "DISP", "GPS"), na=False) &
            ~df["pos_name"].str.contains("CS", na=False)
        )

        df_speed = df[
            df["mobileactivityid"].isin([1, 5]) &
            (df["mobilestatusid"] == "PRD") &
            df["pos_lon"].between(min_lon, max_lon) &
            df["pos_lat"].between(min_lat, max_lat) &
            mask
        ]

        avg_speed = round(float(df_speed["pos_speed"].mean()), 1)
        loaded_speed = round(float(df[df["mobileactivityid"] == 5]["pos_speed"].mean()), 1)
        empty_speed = round(float(df[df["mobileactivityid"] == 1]["pos_speed"].mean()), 1)
        total_dt = df_speed["mobileid"].nunique()
        percentage_slow = round(df_speed[df_speed["pos_speed"] < 18].shape[0] / df_speed.shape[0] * 100, 1)

        segmen_slow = (
            df_speed[(df_speed["pos_speed"] < 18) & (df_speed["pos_speed"] > 1)]
            .groupby("pos_name")
            .agg(
                avg_speed=("pos_speed", "mean"),
                avg_pln_inc=("plm_inc", "mean"),
                count_under=("mobileid", "count"),
                pos_lon=("pos_lon", "mean"),
                pos_lat=("pos_lat", "mean")
            )
            .reset_index()
            .sort_values("count_under", ascending=False)
            .head(5)
        )

        result = {
            "average_speed": avg_speed,
            "loaded_speed": loaded_speed,
            "empty_speed": empty_speed,
            "dottrace_duration_hours": round(duration_hours, 1),
            "total_dt": total_dt,
            "percentage_slow": percentage_slow,
        }

        for i in range(len(segmen_slow)):
            result[f"loc{i+1}"] = segmen_slow["pos_name"].iloc[i]
            result[f"count{i+1}"] = round(float(segmen_slow["avg_speed"].iloc[i]), 1)
            result[f"grade{i+1}"] = round(float(segmen_slow["avg_pln_inc"].iloc[i]), 1)
            result[f"pos_lon{i+1}"] = float(segmen_slow["pos_lon"].iloc[i])
            result[f"pos_lat{i+1}"] = float(segmen_slow["pos_lat"].iloc[i])

        self.analytic_result = result

        df_speed = df_speed[df_speed["pos_speed"] > 1]
        all_speeds = df_speed["pos_speed"].dropna().to_numpy()
        bottom3_units = []
        for u in df_speed.groupby("mobileid")["pos_speed"].mean().sort_values().index:
            speeds = df_speed.loc[df_speed["mobileid"] == u, "pos_speed"].dropna().to_numpy()
            q1, q2, q3 = np.percentile(speeds, [25, 50, 75])
            if q3 - q1 >= 5 and q2 > 1:
                bottom3_units.append(u)
            if len(bottom3_units) == 3:
                break
        data = [all_speeds] + [df_speed.loc[df_speed["mobileid"] == u, "pos_speed"].dropna().to_numpy()
                            for u in bottom3_units]
        labels = ["ALL UNIT"] + [f"{u}" for u in bottom3_units]
        plt.figure(figsize=(8,6))
        box = plt.boxplot(data, labels=labels, patch_artist=True, showfliers=False)
        colors = ["orange"] + ["lightblue"] * (len(data)-1)
        for patch, color in zip(box["boxes"], colors):
            patch.set_facecolor(color)
        for i, d in enumerate(data, start=1):
            q1, q2, q3 = np.percentile(d, [25, 50, 75])
            plt.text(i, q1, f"{q1:.1f}", ha="center", va="bottom", fontsize=12)
            plt.text(i, q2, f"{q2:.1f}", ha="center", va="bottom", fontsize=12)
            plt.text(i, q3, f"{q3:.1f}", ha="center", va="bottom", fontsize=12)
        plt.ylabel("Speed (kph)", fontsize=18, fontweight="bold")
        plt.xticks(fontsize=20, fontweight="bold")
        plt.yticks(fontsize=18, fontweight="bold")
        plt.title("Boxplot of pos_speed (All Units vs Bottom 3 Units)")
        plt.grid(axis="y", linestyle="--", alpha=0.7)
        os.makedirs("templates/asset", exist_ok=True)
        id = uuid.uuid4().hex[:8]
        self.underspeed_chart = rf"templates\asset\underspeed_chart_{id}.png"
        plt.savefig(self.underspeed_chart, bbox_inches="tight", dpi=150)
        self.underspeed_chart = rf"asset\underspeed_chart_{id}.png"
        plt.close()

    def generate(self) -> tuple[str, str]:
        self.query_database()
        self.analyze_dottrace(self.df)
        m = folium.Map(location=self.center, zoom_start=15, tiles="OpenStreetMap", width="80%", height="100%")
        m.fit_bounds(self.bounds)

        card_color = "ef4444" if self.analytic_result["average_speed"] < 23 else "22c55e"
        tpl = open("templates\dt_panel.html", encoding="utf-8").read()
        content_panel = tpl.format(
            image_logo_kpc=self._image_to_base64("asset/logo-kpc.png"),
            image_logo_pama=self._image_to_base64("asset/logo-pama.png"),
            created_at=datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
            region=self.region,
            card_color=card_color,
            underspeed_chart=self.underspeed_chart,
            **self.analytic_result
        )

        m.get_root().html.add_child(folium.Element(content_panel))
        self._add_tif(m)
        self._add_trace(m)

        result = self.analytic_result
        for i in range(1, 6):
            folium.Circle(
                location=[result[f"pos_lat{i}"], result[f"pos_lon{i}"]],
                radius=75,
                color="orange",
                weight=3,
                fill=False,
            ).add_to(m)

        self.html_file = f"templates\dottrace_dt_{uuid.uuid4().hex[:8]}.html"
        self.caption = f"Dot Trace DT {self.region} - {datetime.now():%Y-%m-%d %H:%M}"
        m.save(self.html_file)
        return self.html_file, self.caption

