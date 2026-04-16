from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import geopandas as gpd  # type: ignore
import duckdb

from nird.utils import get_results_variant, load_config
import nird.road_revised as func

import logging
import json
import warnings

warnings.simplefilter("ignore")
base_path = Path(load_config()["paths"]["soge_clusters"])


def first_existing(paths):
    """Return the first existing path from a sequence, else None."""
    for path in paths:
        p = Path(path)
        if p.exists():
            return p
    return None


def main(
    num_of_chunk: int,
    num_of_cpu: int,
    sample_stride=1,
):
    """
    Main function to validate the network flow model.

    Model Inputs:
        - Model parameters:
            - Flow breakpoints, capacity, free-flow speeds, minimum speeds,
            and urban speed limits.
        - faf5_road_links.gpq:
            GeoDataFrame containing FAF5 road network data with attributes.
        - faf5_od_matrix.pq:
            Origin-destination matrix containing FAF5 traffic flow data.

    Model Outputs:
        - edge_flows_validation.gpq:
            GeoDataFrame of road network data enriched with validation results.
        - trip_isolation_validation.csv:
            CSV file containing data on isolated trips resulting from network
            disruptions.

    Parameters:
        num_of_cpu (int): Number of CPUs to use for parallel processing.
        sample_stride (int): Stride length to use on OD. Defaults to using
            entire matrix.

    Returns:
        None: Outputs are saved to files.
    """
    start_time = time.time()
    db_path = base_path / "dbs" / "baseline.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info(f"Database path is: {db_path}")

    # model parameters

    params_root = first_existing(
        [
            base_path / "parameters",
            base_path / "inputs" / "parameters",
        ]
    )
    if params_root is None:
        raise FileNotFoundError(
            "Could not find parameter folder. Checked base_path/parameters and base_path/inputs/parameters"
        )

    # model parameters
    with open(params_root / "flow_breakpoint_dict.json", "r") as f:
        flow_breakpoint_dict = json.load(f)
    with open(params_root / "flow_cap_plph_dict.json", "r") as f:
        flow_capacity_dict = json.load(f)
    with open(params_root / "free_flow_speed_dict.json", "r") as f:
        free_flow_speed_dict = json.load(f)
    with open(params_root / "min_speed_cap.json", "r") as f:
        min_speed_dict = json.load(f)
    with open(params_root / "urban_speed_cap.json", "r") as f:
        urban_speed_dict = json.load(f)
    logging.info(flow_capacity_dict)

    # network links -> network links with bridges (SUBNETWORK)
    road_links_path = first_existing(
        [
            base_path / "networks" / "faf5" / "faf5_road_links.gpq",
            base_path / "inputs" / "networks" / "faf5" / "faf5_road_links.gpq",
        ]
    )
    if road_links_path is None:
        raise FileNotFoundError("Could not find faf5_road_links.gpq in standard or toy input paths")
    road_link_file = gpd.read_parquet(road_links_path)

    # od matrix (2021)
    od_path = first_existing(
        [
            base_path / "census_datasets" / "faf5_od_matrix.pq",
            base_path / "inputs" / "census_datasets" / "faf5_od_matrix.pq",
            base_path / "inputs" / "test_17node" / "faf5_od_matrix_17x17_test.pq",
        ]
    )
    if od_path is None:
        raise FileNotFoundError("Could not find FAF5 OD matrix in standard or toy input paths")
    od_node_2021 = pd.read_parquet(od_path)

    if sample_stride > 1:
        logging.info(f"For testing, sampling every {sample_stride} flows")
        od_node_2021 = od_node_2021.iloc[::sample_stride]

    logging.info(f"\n{od_node_2021}")
    logging.info(f"Total flows: {od_node_2021.Car21.sum()}")

    # initialise road links
    logging.info("Generate road links")
    road_links = func.edge_init(
        road_link_file,
        flow_breakpoint_dict,
        flow_capacity_dict,
        free_flow_speed_dict,
        urban_speed_dict,
        min_speed_dict,
        max_flow_speed_dict=None,
    )
    # create igraph network
    logging.info("Create igraph network")
    network, road_links = func.create_igraph_network(road_links, vehicle_type="car")
    # run flow simulation
    logging.info("Run simulation")
    (
        road_links,
        cList,
    ) = func.network_flow_model(
        road_links,
        network,
        od_node_2021,
        flow_breakpoint_dict,
        num_of_chunk,
        num_of_cpu,
        db_path,
    )
    
    # Read isolation and odpfc from database
    conn = duckdb.connect(db_path)
    isolation = conn.execute("SELECT * FROM isolated_od").fetchall()
    odpfc = conn.execute("SELECT * FROM odpfc").fetchall()
    conn.close()
    
    # isolation
    isolation_df = pd.DataFrame(
        isolation,
        columns=[
            "origin_node",
            "destination_node",
            "flow",
        ],
    )
    isolation_df = isolation_df[
        (isolation_df.origin_node != isolation_df.destination_node)
        & (isolation_df.flow > 0)
    ].reset_index(drop=True)

    # odpfc
    odpfc_df = pd.DataFrame(
        odpfc,
        columns=[
            "origin_node",
            "destination_node",
            "path",
            "flow",
            "operating_cost_per_flow",
            "time_cost_per_flow",
            "toll_cost_per_flow",
            "fare_cost_per_flow",
        ],
    )
    odpfc_df.path = odpfc_df.path.apply(tuple)
    odpfc_df = odpfc_df.groupby(
        by=["origin_node", "destination_node", "path"], as_index=False
    ).agg(
        {
            "flow": "sum",
            "operating_cost_per_flow": "first",
            "time_cost_per_flow": "first",
            "toll_cost_per_flow": "first",
        }
    )

    # export files
    out_path = base_path.parent / "results" / "base_scenario" / get_results_variant()
    out_path.mkdir(parents=True, exist_ok=True)
    road_links.to_parquet(out_path / "edge_flows.gpq")
    isolation_df.to_parquet(out_path / "trip_isolations.pq")
    odpfc_df.to_parquet(out_path / "odpfc.pq")
    logging.info(f"The total simulation time: {time.time() - start_time}")


if __name__ == "__main__":
    """
    Entry point of the script. Reads the number of CPUs from command-line arguments
    and calls the main function.

    Command-line Arguments:
        num_of_cpu (int): Number of CPUs to use for parallel processing.
        sample_stride (int): Stride length to use on OD.

    Returns:
        None: Prints a message if the required argument is missing.
    """
    logging.basicConfig(
        format="%(asctime)s %(process)d %(filename)s %(message)s", level=logging.INFO
    )
    try:  # in bash inputs will be str by default
        sample_stride = 1
        num_of_chunk = sys.argv[1]
        num_of_cpu = sys.argv[2]
        main(int(num_of_chunk), int(num_of_cpu), sample_stride)
    except (IndexError, NameError):
        logging.info("Please enter num_of_chunk, num_of_cpu!")
