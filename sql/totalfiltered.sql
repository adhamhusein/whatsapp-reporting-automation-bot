

SELECT STUFF((
    SELECT '; ' + UnitEgi + ':' + CAST(COUNT(*) AS VARCHAR)
    FROM db_ewacs_fgdp.dbo.unit
    WHERE UnitEgi IS NOT NULL 
		and unitstatus = '{unitstatus}' and UnitEqClass = '{UnitEqClass}' and UnitSubcontName = '{UnitSubcontName}'
    GROUP BY UnitEgi
    ORDER BY UnitEgi
    FOR XML PATH(''), TYPE
).value('.', 'NVARCHAR(MAX)'), 1, 2, '');



