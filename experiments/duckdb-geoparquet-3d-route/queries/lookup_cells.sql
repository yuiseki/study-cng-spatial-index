-- Generic blocked-cell lookup for A* route search.
-- Load all blocked (x, y) pairs in a bounding box + altitude band.

-- zfxy variant:
SELECT DISTINCT x, y
FROM read_parquet('data/parquet/occupancy_zfxy.parquet')
WHERE zfxy_z = $z
  AND f BETWEEN $f_min AND $f_max
  AND x BETWEEN $x_lo  AND $x_hi
  AND y BETWEEN $y_lo  AND $y_hi;

-- zxy_heightbin variant:
-- SELECT DISTINCT x, y
-- FROM read_parquet('data/parquet/occupancy_zxy_heightbin.parquet')
-- WHERE xy_z = $xy_z AND vertical_bin_m = $vbin
--   AND hbin BETWEEN $hbin_min AND $hbin_max
--   AND x BETWEEN $x_lo AND $x_hi
--   AND y BETWEEN $y_lo AND $y_hi;
