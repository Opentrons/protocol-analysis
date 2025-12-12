"""End-to-end test for protocol evaluation workflow."""

import asyncio
import os
from pathlib import Path

import pytest

from client.evaluate_client import AsyncEvaluationClient

POLL_INTERVAL = 0.2


@pytest.mark.asyncio
async def test_evaluate_protocol_e2e():
    """Test the complete workflow of submitting and evaluating a protocol."""
    # Path to the baseline test protocol
    protocol_file = Path("test-files/simple/Flex_S_v2_24_P50_PAPI_Changes.py")
    custom_protocol_file = Path(
        "test-files/custom-labware-only/Flex_S_v2_25_P50_P200_stacker_all_parts.py"
    )
    custom_labware_files = [
        Path(
            "test-files/custom-labware-only/custom_opentrons_tough_pcr_auto_sealing_lid.json"
        ),
        Path(
            "test-files/custom-labware-only/stackable_opentrons_96_wellplate_200ul_pcr_full_skirt.json"
        ),
    ]
    csv_protocol_file = Path("test-files/rtp-csv-only/OpentronsAI_CSV.py")
    csv_data_file = Path("test-files/rtp-csv-only/plates.csv")
    custom_csv_protocol_file = Path(
        "test-files/only-not-rtp-override/OpentronsAI_CSV_AND_CustomLabware.py"
    )
    custom_csv_labware_file = Path(
        "test-files/only-not-rtp-override/eppendorf_96_wellplate_150ul.json"
    )
    custom_csv_data_file = Path("test-files/only-not-rtp-override/plates.csv")

    assert protocol_file.exists(), f"Protocol file not found: {protocol_file}"
    assert custom_protocol_file.exists(), (
        f"Protocol file not found: {custom_protocol_file}"
    )
    for labware_path in custom_labware_files:
        assert labware_path.exists(), f"Labware file not found: {labware_path}"
    assert csv_protocol_file.exists(), f"Protocol file not found: {csv_protocol_file}"
    assert csv_data_file.exists(), f"CSV file not found: {csv_data_file}"
    assert custom_csv_protocol_file.exists(), (
        f"Protocol file not found: {custom_csv_protocol_file}"
    )
    assert custom_csv_labware_file.exists(), (
        f"Labware file not found: {custom_csv_labware_file}"
    )
    assert custom_csv_data_file.exists(), f"CSV file not found: {custom_csv_data_file}"

    async with AsyncEvaluationClient() as client:
        # Verify API + processor readiness before submitting jobs.
        # This avoids flakiness if the processor hasn't written its first heartbeat yet.
        ready = None
        for _ in range(50):  # ~10s max
            ready = await client.get_ready(processor_max_age_seconds=60)
            if ready.get("api") == "ok" and ready.get("processor_ready") is True:
                break
            await asyncio.sleep(POLL_INTERVAL)

        assert ready is not None
        assert ready["api"] == "ok"
        assert ready["processor_ready"] is True

        # Check API info
        info = await client.get_info()
        assert info["version"] == "0.1.0"
        assert "protocol_api_versions" in info
        assert "supported_robot_versions" in info
        assert len(info["supported_robot_versions"]) > 0

        enable_edge = os.getenv("PROTOCOL_EVALUATION_ENABLE_EDGE", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        submit_tasks = {
            "8.7.0": client.submit_protocol(protocol_file, robot_version="8.7.0"),
            "next": client.submit_protocol(protocol_file, robot_version="next"),
            "custom": client.submit_protocol(
                custom_protocol_file,
                robot_version="8.7.0",
                labware_files=custom_labware_files,
            ),
            "csv": client.submit_protocol(
                csv_protocol_file,
                robot_version="8.7.0",
                csv_file=csv_data_file,
            ),
            "custom_csv": client.submit_protocol(
                custom_csv_protocol_file,
                robot_version="8.7.0",
                labware_files=[custom_csv_labware_file],
                csv_file=custom_csv_data_file,
            ),
        }
        if enable_edge:
            submit_tasks["edge"] = client.submit_protocol(
                protocol_file, robot_version="edge"
            )

        submit_keys = list(submit_tasks.keys())
        submit_results = await asyncio.gather(*[submit_tasks[k] for k in submit_keys])
        job_ids = dict(zip(submit_keys, submit_results, strict=True))

        assert all(job_id for job_id in job_ids.values())

        # Poll for completion of both jobs
        status_tasks = {
            key: client.wait_for_completion(job_id, poll_interval=POLL_INTERVAL)
            for key, job_id in job_ids.items()
        }
        status_keys = list(status_tasks.keys())
        status_results = await asyncio.gather(*[status_tasks[k] for k in status_keys])
        statuses = dict(zip(status_keys, status_results, strict=True))

        assert statuses["8.7.0"]["status"] == "completed"
        assert statuses["next"]["status"] == "completed"
        assert statuses["custom"]["status"] == "completed"
        assert statuses["csv"]["status"] == "completed"
        assert statuses["custom_csv"]["status"] == "completed"
        if enable_edge:
            assert statuses["edge"]["status"] == "completed"

        # Get and verify results for 8.7.0
        result_tasks = {
            key: client.get_job_result(job_id) for key, job_id in job_ids.items()
        }
        result_keys = list(result_tasks.keys())
        result_results = await asyncio.gather(*[result_tasks[k] for k in result_keys])
        results = dict(zip(result_keys, result_results, strict=True))

        result_870 = results["8.7.0"]
        assert result_870["status"] == "completed"
        assert result_870["result_type"] == "analysis"
        assert result_870["result"] is not None
        assert result_870["result"]["status"] == "success"
        assert result_870["result"]["robot_version"] == "8.7.0"
        assert result_870["result"]["analysis"]["result"] == "ok"

        # Get and verify results for 'next'
        result_next = results["next"]
        assert result_next["status"] == "completed"
        assert result_next["result_type"] == "analysis"
        assert result_next["result"] is not None
        assert result_next["result"]["status"] == "success"
        assert result_next["result"]["robot_version"] == "next"
        assert result_next["result"]["analysis"]["result"] == "ok"

        # Get and verify results for 'edge' (optional)
        if enable_edge:
            result_edge = results["edge"]
            assert result_edge["status"] == "completed"
            assert result_edge["result_type"] == "analysis"
            assert result_edge["result"] is not None
            assert result_edge["result"]["status"] == "success"
            assert result_edge["result"]["robot_version"] == "edge"
            assert result_edge["result"]["analysis"]["result"] == "ok"

        # Get and verify results for protocol with custom labware
        result_custom = results["custom"]
        assert result_custom["status"] == "completed"
        assert result_custom["result_type"] == "analysis"
        assert result_custom["result"] is not None
        assert result_custom["result"]["status"] == "success"
        assert result_custom["result"]["robot_version"] == "8.7.0"
        assert result_custom["result"]["analysis"]["result"] == "ok"

        analyzed_labware = result_custom["result"]["files_analyzed"]["labware_files"]
        assert analyzed_labware is not None, "Expected labware files in analysis output"
        expected_labware_names = {path.name for path in custom_labware_files}
        assert set(analyzed_labware) >= expected_labware_names

        # Get and verify results for protocol with CSV input
        result_csv = results["csv"]
        assert result_csv["status"] == "completed"
        assert result_csv["result_type"] == "analysis"
        assert result_csv["result"] is not None
        assert result_csv["result"]["status"] == "success"
        assert result_csv["result"]["robot_version"] == "8.7.0"
        assert result_csv["result"]["analysis"]["result"] == "ok"
        analyzed_csv = result_csv["result"]["files_analyzed"]["csv_file"]
        assert analyzed_csv, "Expected csv file in analysis output"
        assert analyzed_csv == csv_data_file.name

        # Get and verify results for protocol requiring both labware and CSV
        result_custom_csv = results["custom_csv"]
        assert result_custom_csv["status"] == "completed"
        assert result_custom_csv["result_type"] == "analysis"
        assert result_custom_csv["result"] is not None
        assert result_custom_csv["result"]["status"] == "success"
        assert result_custom_csv["result"]["robot_version"] == "8.7.0"
        assert result_custom_csv["result"]["analysis"]["result"] == "ok"
        analyzed_custom_csv = result_custom_csv["result"]["files_analyzed"]
        assert analyzed_custom_csv["csv_file"] == custom_csv_data_file.name
        assert custom_csv_labware_file.name in analyzed_custom_csv["labware_files"]

        # Fetch simulation outputs for every job
        sim_tasks = {
            key: client.get_job_result(job_id, result_type="simulation")
            for key, job_id in job_ids.items()
        }
        sim_keys = list(sim_tasks.keys())
        sim_results = await asyncio.gather(*[sim_tasks[k] for k in sim_keys])
        sims = dict(zip(sim_keys, sim_results, strict=True))

        # Jobs without CSV inputs should have full simulation data
        expected_full_sim = [
            ("8.7.0", "8.7.0"),
            ("next", "next"),
            ("custom", "8.7.0"),
        ]
        if enable_edge:
            expected_full_sim.append(("edge", "edge"))

        for key, robot_version in expected_full_sim:
            sim_result = sims[key]
            assert sim_result["status"] == "completed"
            assert sim_result["result_type"] == "simulation"
            assert sim_result["result"] is not None
            assert sim_result["result"]["status"] == "success"
            assert sim_result["result"]["robot_version"] == robot_version
            assert "simulation" in sim_result["result"]

        # Jobs with CSV inputs should skip simulation with an explanatory reason
        for key in ("csv", "custom_csv"):
            sim_result = sims[key]
            assert sim_result["status"] == "completed"
            assert sim_result["result_type"] == "simulation"
            assert sim_result["result"] is not None
            assert sim_result["result"]["status"] == "skipped"
            assert "runtime parameter CSV input" in sim_result["result"]["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
