import os
import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import pyodbc, uuid

class BottomSpeed:
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
        self.df = None
        self.caption = None
        self.underspeed_chart = None

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
        self.underspeed_chart = rf"underspeed_chart_{id}.png"
        plt.savefig(self.underspeed_chart, bbox_inches="tight", dpi=150)
        plt.close()

    def generate(self) -> tuple[str, str]:
        self.query_database()
        self.analyze_dottrace(self.df)
        self.caption = f"Bottom Speed {self.region} - {datetime.now():%Y-%m-%d %H:%M}"
        return self.underspeed_chart, self.caption
