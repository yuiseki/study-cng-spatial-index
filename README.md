# study-cng-spatial-index

**CNG / file-based index 環境における空間インデックス設計の比較検証リポジトリ。**

PostGIS GiST を持たない Cloud Native Geospatial / edge / DuckDB / Parquet 環境で、
2D・3D 各種 key design が最も実用的かを実測します。

## このリポジトリの目的

```
PostGIS GiST がない CNG / edge / file-based index 環境で、
(1) 2D 空間クエリ（viewport / radius）と
(2) 3D occupancy grid による経路探索
を行う場合、どの key design が最も少ないファイルスキャン・少ない lookup・小さい index size で済むか。
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

---

## 実験 1: 2D 空間インデックス比較

詳細: [`experiments/duckdb-geoparquet-2d/README.md`](experiments/duckdb-geoparquet-2d/README.md)

### 比較する 5 つの scheme

| scheme | key | sort key | 特徴 |
|--------|-----|----------|------|
| **H3** | 六角形セル文字列 | (resolution, h3_cell) | 均等面積、res=7–10 |
| **GeoHash** | Base32 文字列 | (precision, geohash) | 文字列プレフィックス局所性 |
| **Quadkey** | Web Mercator タイル文字列 | (zoom, quadkey) | Web 地図タイルと完全互換 |
| **Morton2D** | uint64 Z-order key | (zoom, key_u64) | single sorted key、box query で OR ranges |
| **bbox-cols** | xmin/ymin/xmax/ymax | (xmin) | Parquet column statistics で自動 pruning |

### クエリ種別

- **viewport**: 矩形範囲内の点・建物を返す（0.01° / 0.05° / 0.1° 幅）
- **radius**: 中心点から半径 r 内の点（H3 grid_disk 近似）（500 m / 1,000 m / 2,000 m）

### 実測結果サマリ（台東区 OSM 25,821 点 / 36,521 建物）

#### viewport_points（vp=0.01° ≈ 1 km 四方）

| scheme | resolution | n_cells | count | avg_ms |
|--------|-----------|---------|-------|--------|
| **bbox_cols** | — | — | **3,400** | **2.2** |
| Morton2D | z=19 | 8 ranges | 3,874 | 2.0 |
| H3 | res=9 | 10 cells | 3,022 | 2.1 |
| GeoHash | prec=7 | 72 cells | 4,344 | 2.7 |
| Quadkey | z=17 | 24 cells | 4,641 | 2.4 |

#### viewport_points（vp=0.10° ≈ 10 km 四方）— IN 述語崩壊ゾーン

| scheme | resolution | n_cells | avg_ms |
|--------|-----------|---------|--------|
| **bbox_cols** | — | — | **3.9** |
| Quadkey | z=15 | 132 cells | 5.6 |
| Morton2D | z=19 | 252 ranges | 9.6 |
| GeoHash | prec=7 | 5,402 cells | 20.9 |
| H3 | res=10 | 7,253 cells | 28.3 |
| Quadkey | z=19 | 26,460 cells | **92.3** |
| GeoHash | prec=8 | 170,236 cells | **538.7** |

#### 結論

1. **bbox-cols が最速・最正確。** viewport サイズに関わらず 2–5 ms で安定。
2. **IN 述語は ~500 cells 超で線形劣化する。** 大 viewport × 高解像度で GeoHash prec=8: 539 ms、Quadkey z=19: 92 ms に到達。
3. **各 scheme のスイートスポット:** H3 res=8–9 / GeoHash prec=6–7 / Quadkey z=15–17 が 2–11 ms 以内。
4. **Morton2D（BETWEEN ranges）は IN overhead を回避でき最大 252 ranges で 10 ms 以内。** 3D Morton より大幅に良好。

詳細: [`experiments/duckdb-geoparquet-2d/README.md`](experiments/duckdb-geoparquet-2d/README.md)

### 実行方法

```bash
# データ準備（PostgreSQL が localhost:55442 で動いている必要あり）
make prepare-2d

# 2D ベンチマーク
make bench-2d
```

---

## 実験 2: 3D 空間インデックス比較（drone corridor lookup + A* route）

詳細: [`experiments/duckdb-geoparquet-3d-route/README.md`](experiments/duckdb-geoparquet-3d-route/README.md)

### 比較する 3 つの key design

#### A. zfxy
```
key = {z}/{f}/{x}/{y}
f = floor(2^z * h / 2^25)
```
水平解像度と垂直解像度が **同じ z に束縛される**。
per-floor 粒度には z≥24 が必要だが、そのとき x/y は ~1 m/tile になる。

#### B. zxy + independent height bin
```
key = {xy_z}/{x}/{y}/{vertical_bin_m}/{hbin}
hbin = floor(h / vertical_bin_m)
```
水平解像度（`xy_z`）と垂直解像度（`vertical_bin_m`）を **独立に設計できる**。
例: xy_z=19（~5 m/tile）、vertical_bin_m=4m で 4 m/bin の高さ粒度。

#### C. 3D Morton / Z-order key
```
key_u64 = interleave_bits(local_x, local_y, hbin)
```
単一の sortable key として Parquet / KV / Range Request に載せやすい。
ただし box query には interval decomposition が必要になる。

### 実測結果サマリ（台東区 OSM 36,521 建物）

#### corridor 候補建物数（alt=30m, clearance=±5m）

| scheme | resolution | candidates | actual | FP% | query (ms) |
|--------|-----------|------------|--------|-----|------------|
| zfxy | z=19 | 3,183 | 16 | 99.5% | 3.6 |
| zfxy | z=21 | 51 | 16 | 68.6% | 2.4 |
| zfxy | z=22 | 26 | 16 | 38.5% | 3.0 |
| **zxy_hbin** | **vbin=4m** | **34** | **16** | **52.9%** | **2.7** |
| Morton3D | vbin=4m | 41 | 16 | 61.0% | **14.8** |

#### A* route search（corridor 100m width）

| scheme | alt=30m | alt=60m | alt=90m |
|--------|---------|---------|---------|
| zfxy z=19 | ✗ | ✗（f=0 過多で全閉塞） | ✓ |
| zfxy z=22 | ✓ | ✓ | ✓ |
| zxy_hbin vbin=4m | ✗ | ✓ | ✓ |

alt=30m は 16 棟の建物が corridor を閉塞するため全 scheme で経路なし。

#### 結論

1. **zxy_heightbin (vbin=4–8m) が最もバランスよい。**
   ファイル 2 MB、候補 34 件、クエリ ~2 ms。
2. **zfxy は z=21–22 で comparable になるが 4 zoom level 分のファイルが必要（5 MB）。**
3. **Morton3D は box query に向かない。OR 分解数 85–136 で ~15 ms。**

### 実行方法

```bash
# データ準備（PostgreSQL が localhost:55442 で動いている必要あり）
make prepare

# Stage 1: corridor lookup benchmark
make bench-corridor

# Stage 2: A* route search benchmark
make bench-route

# 結果集計
make summarize
```

---

## 全体の実行方法

```bash
# 1. 依存関係のインストール
make install

# 2a. 3D 実験データ準備 + ベンチマーク
make all

# 2b. 2D 実験データ準備 + ベンチマーク
make all-2d
```

## ディレクトリ構成

```
study-cng-spatial-index/
  README.md
  pyproject.toml
  Makefile
  src/cng_spatial_index/
    config.py               パス・パラメータ定数（2D / 3D 両方）
    height_model.py         OSM height タグ parse + 高さモデル
    h3_key.py               H3 encode（point / bbox / disk）
    geohash_key.py          GeoHash encode + BFS bbox cover
    quadkey.py              Quadkey encode（mercantile）
    morton2d.py             2D Z-order key
    zfxy.py                 zfxy 3D key 関数
    zxy_heightbin.py        zxy + height bin key 関数
    morton3d.py             3D Morton key（bit interleave）
    occupancy.py            建物 → 3D セル展開
    duckdb_queries.py       DuckDB corridor lookup クエリ
    route.py                A* グリッド経路探索
    metrics.py              ファイル統計・summary 生成
  scripts/
    prepare_osm_buildings.py    PostgreSQL → 建物 GeoJSON
    prepare_osm_points.py       PostgreSQL → 点フィーチャー GeoJSON
    build_obstacles_geoparquet.py  高さモデル付き GeoParquet 作成
    build_occupancy_cells.py    3D occupancy Parquet 作成
    build_2d_cells.py           2D セル Parquet 作成（全 scheme）
    run_corridor_bench.py       3D corridor lookup bench
    run_route_bench.py          A* route search bench
    run_2d_bench.py             2D viewport / radius bench
    summarize_results.py        結果集計
  experiments/
    duckdb-geoparquet-2d/       2D インデックス比較実験
    duckdb-geoparquet-3d-route/ 3D route 探索実験
```

## 制約

- OSM データ取得は PostgreSQL 経由（`prepare_osm_*.py` のみ PostGIS 依存）
- その後の全ステップは PostGIS 不要
- occupancy / 2D cell は bbox footprint cover（strict polygon cover ではない）
- corridor は bbox 矩形近似
- Morton interval decomposition は naive gap_factor merging
- object storage での range request 効率は未計測（local filesystem のみ）
- Overture Maps 対応は未実装（OSM 台東区で完結）
