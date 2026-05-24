-- zfxy corridor lookup
-- Variables: $x_min, $x_max, $y_min, $y_max, $f_min, $f_max
-- Sort order: (zfxy_z, f, x, y) → row-group pruning on f and x/y range

SELECT DISTINCT osm_id
FROM read_parquet('data/parquet/occupancy_zfxy.parquet')
WHERE zfxy_z  = $z
  AND f  BETWEEN $f_min  AND $f_max
  AND x  BETWEEN $x_min  AND $x_max
  AND y  BETWEEN $y_min  AND $y_max;
