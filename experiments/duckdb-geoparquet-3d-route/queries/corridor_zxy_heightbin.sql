-- zxy + height_bin corridor lookup
-- Sort order: (xy_z, vertical_bin_m, hbin, x, y)
-- Row-group pruning on hbin range is effective when vbin is fine-grained

SELECT DISTINCT osm_id
FROM read_parquet('data/parquet/occupancy_zxy_heightbin.parquet')
WHERE xy_z         = $xy_z
  AND vertical_bin_m = $vertical_bin_m
  AND hbin BETWEEN $hbin_min AND $hbin_max
  AND x    BETWEEN $x_min    AND $x_max
  AND y    BETWEEN $y_min    AND $y_max;
