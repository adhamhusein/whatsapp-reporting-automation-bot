

SELECT STUFF((
    SELECT '; ' + UnitEgi + ':' + CAST(COUNT(*) AS VARCHAR)
    FROM db_ewacs_fgdp.dbo.unit
    WHERE unitstatus = 1 AND UnitEgi IS NOT NULL
    GROUP BY UnitEgi
    ORDER BY UnitEgi
    FOR XML PATH(''), TYPE
).value('.', 'NVARCHAR(MAX)'), 1, 2, '');

