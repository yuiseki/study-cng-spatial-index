# study-cng-spatial-index

**CNG / file-based index 環境における 3D 空間キー設計の比較検証リポジトリ。**

PostGIS GiST を持たない Cloud Native Geospatial / edge / DuckDB / Parquet 環境で、
どの key design が最も実用的かを実測します。

## このリポジトリの目的

```
PostGIS GiST がない CNG / edge / file-based index 環境で、
3D occupancy grid による経路探索を行う場合、
どの key design が最も少ないファイルスキャン・少ない lookup・小さい index size で済むか。
```

## study-pg-spatial-index との違い

[`study-pg-spatial-index`](https://github.com/yuiseki/study-pg-spatial-index) では
PostgreSQL / PostGIS 上で GiST / SP-GiST / BRIN / H3 / GeoHash / Q3C / HEALPix / zfxy を比較しました。

結論: **PostGIS GiST + numeric height range が最強。zfxy 3D B-tree に競争優位はなかった。**

しかし、CNG / edge では常に PostGIS GiST が使えるとは限りません。
このリポジトリは **GiST なし** の前提で、DuckDB + GeoParquet / Parquet 上の key design を比較します。

## PostGIS GiST を使わない理由

- Cloud Native Geospatial の文脈では、データは object storage に Parquet / GeoParquet として存在する
- クエリは DuckDB / Athena / BigQuery などから発行される
- GiST は PostgreSQL 固有の機能。Parquet には row group min/max statistics しかない
- **row group pruning が GiST の代替**になるため、key の sort order が重要

## DuckDB + GeoParquet / Parquet を使う理由

- Parquet は columnar format で min/max statistics による row group skipping が効く
- ソートされた key であれば DuckDB は適切な row group を skip できる
- GiST なしで空間インデックスを模倣できるか検証できる
- Python から直接使え、PostgreSQL のインスタンスが不要

## 比較する 3 つの key design

### A. zfxy
```
key = {z}/{f}/{x}/{y}
f = floor(2^z * h / 2^25)
```
水平解像度と垂直解像度が **同じ z に束縛される**。
per-floor 粒度には z≥24 が必要だが、そのとき x/y は ~1 m/tile になる。

### B. zxy + independent height bin
```
key = {xy_z}/{x}/{y}/{vertical_bin_m}/{hbin}
hbin = floor(h / vertical_bin_m)
```
水平解像度（`xy_z`）と垂直解像度（`vertical_bin_m`）を **独立に設計できる**。
例: xy_z=19（~5 m/tile）、vertical_bin_m=4m で 4 m/bin の高さ粒度。

### C. 3D Morton / Z-order key
```
key_u64 = interleave_bits(local_x, local_y, hbin)
```
単一の sortable key として Parquet / KV / Range Request に載せやすい。
ただし box query には interval decomposition が必要になる。

## 期待する観察（仮説）

- PostGIS がある環境では GiST が勝つ（study-pg-spatial-index で実証済み）
- GiST がない CNG 環境では sorted key + row group pruning が代替になる
- **zfxy は比較対象として有用だが、水平と垂直の解像度が同じ z に束縛されるため 3D route lookup では不器用**
- **zxy + independent height bin は水平・垂直を独立調整できるため CNG 向け 3D key として有力**
- **Morton3D は single sortable key として理論上美しいが、box query での range 分解数が多くなり DuckDB では OR overhead が支配的になる可能性がある**

## 実測結果サマリ（台東区 OSM 36,521 建物）

### corridor 候補建物数（alt=30m, clearance=±5m）

| scheme | resolution | candidates | actual | FP% | query (ms) |
|--------|-----------|------------|--------|-----|------------|
| zfxy | z=19 | 3,183 | 16 | 99.5% | 3.6 |
| zfxy | z=21 | 51 | 16 | 68.6% | 2.4 |
| zfxy | z=22 | 26 | 16 | 38.5% | 3.0 |
| **zxy_hbin** | **vbin=4m** | **34** | **16** | **52.9%** | **2.7** |
| Morton3D | vbin=4m | 41 | 16 | 61.0% | **14.8** |

### zfxy f 粒度問題（再掲）

| z | m/f-unit | cands@alt30m |
|---|----------|-------------|
| 19 | 64 m | 3,183 （f=0 で全件スキャン） |
| 21 | 16 m | 51 |
| 22 | 8 m | 26 |

### A* route search（corridor 100m width）

| scheme | alt=30m | alt=60m | alt=90m |
|--------|---------|---------|---------|
| zfxy z=19 | ✗ | ✗（f=0 過多で全閉塞） | ✓ |
| zfxy z=22 | ✓ | ✓ | ✓ |
| zxy_hbin vbin=4m | ✗ | ✓ | ✓ |

alt=30m は 16 棟の建物が corridor を閉塞するため全 scheme で経路なし。

### 結論

1. **zxy_heightbin (vbin=4–8m) が最もバランスよい。**
   ファイル 2 MB、候補 34 件、クエリ ~2 ms。
2. **zfxy は z=21–22 で comparable になるが 4 zoom level 分のファイルが必要（5 MB）。**
3. **Morton3D は box query に向かない。OR 分解数 85–136 で ~15 ms。**

詳細: [`experiments/duckdb-geoparquet-3d-route/README.md`](experiments/duckdb-geoparquet-3d-route/README.md)

## 実行方法

```bash
# 1. 依存関係のインストール
make install

# 2. データ準備（PostgreSQL → GeoJSON → GeoParquet → occupancy Parquet）
#    study-pg-spatial-index の zfxy コンテナが localhost:55442 で動いている必要があります
make prepare

# 3. Stage 1: corridor lookup benchmark
make bench-corridor

# 4. Stage 2: A* route search benchmark
make bench-route

# 5. 結果集計
make summarize

# まとめて実行
make all
```

## 期待する出力

```
data/raw/buildings_taito.geojson          OSM 台東区建物 GeoJSON
data/prepared/building_obstacles.geoparquet  高さモデル付き障害物 GeoParquet
data/parquet/occupancy_zfxy.parquet        zfxy セル lookup table
data/parquet/occupancy_zxy_heightbin.parquet  zxy+hbin セル lookup table
data/parquet/occupancy_morton3d.parquet    Morton3D セル lookup table
data/results/<timestamp>/
  metadata.json
  summary.csv
  summary.md
  explain/*.txt     DuckDB EXPLAIN ANALYZE
  queries/*.sql     実行したクエリ
```

## ディレクトリ構成

```
study-cng-spatial-index/
  README.md
  pyproject.toml
  Makefile
  src/cng_spatial_index/
    config.py           パス・corridor・パラメータ定数
    height_model.py     OSM height タグ parse + 高さモデル
    zfxy.py             zfxy key 関数
    zxy_heightbin.py    zxy + height bin key 関数
    morton3d.py         3D Morton key (bit interleave)
    occupancy.py        建物 → セル展開
    duckdb_queries.py   DuckDB corridor lookup クエリ
    route.py            A* グリッド経路探索
    metrics.py          ファイル統計・summary 生成
  scripts/
    prepare_osm_buildings.py   PostgreSQL → GeoJSON（PostGIS 依存はここだけ）
    build_obstacles_geoparquet.py  高さモデル付き GeoParquet 作成
    build_occupancy_cells.py   occupancy Parquet 作成
    run_corridor_bench.py      Stage 1: corridor lookup
    run_route_bench.py         Stage 2: A* route search
    summarize_results.py       結果集計
  experiments/
    duckdb-geoparquet-3d-route/
      README.md         実験詳細・結果テーブル
      queries/          SQL テンプレート
```

## 制約

- OSM データ取得は PostgreSQL 経由（`prepare_osm_buildings.py` のみ PostGIS 依存）
- その後の全ステップは PostGIS 不要
- occupancy cells は bbox footprint cover（strict polygon cover ではない）
- corridor は bbox 矩形近似
- Morton3D interval decomposition は naive gap_factor merging
- object storage での range request 効率は未計測（local filesystem のみ）
- Overture Maps 対応は未実装（OSM 台東区で完結）
