SELECT 
	'*Berikut ini detail status unit yang diminta:*' +
    ';Unit: ' + UnitEqNum + 
    ';EGI: ' + UnitEgi + 
    ';Class: ' + UnitEqClass + 
    ';Desc: ' + UnitKeterangan + 
    ';IBS: ' + UnitEqClassIBS + 
    ';Updated: ' + CONVERT(VARCHAR(19), update_at, 120)
FROM db_ewacs_fgdp.dbo.unit
WHERE UnitEqNum = '{UnitEqNum}' AND unitstatus = 1;