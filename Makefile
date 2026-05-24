.PHONY: install prepare prepare-2d bench-corridor bench-route bench-2d summarize all clean

install:
	uv sync

prepare:
	uv run python scripts/prepare_osm_buildings.py
	uv run python scripts/build_obstacles_geoparquet.py
	uv run python scripts/build_occupancy_cells.py

prepare-cells:
	uv run python scripts/build_occupancy_cells.py

bench-corridor:
	uv run python scripts/run_corridor_bench.py

bench-route:
	uv run python scripts/run_route_bench.py

summarize:
	uv run python scripts/summarize_results.py

all: prepare bench-corridor summarize

# Run with a specific row group size
bench-rg:
	uv run python scripts/build_occupancy_cells.py --row-group-size $(RG_SIZE)
	uv run python scripts/run_corridor_bench.py

prepare-2d:
	uv run python scripts/prepare_osm_points.py
	uv run python scripts/build_2d_cells.py

bench-2d:
	uv run python scripts/run_2d_bench.py

all-2d: prepare-2d bench-2d

clean:
	rm -rf data/raw/*.geojson data/prepared/*.parquet data/prepared/*.geoparquet \
	       data/parquet/*.parquet data/results/
