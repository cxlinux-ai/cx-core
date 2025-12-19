from intent.detector import Intent
from intent.planner import InstallationPlanner


def test_planner_cuda_pipeline():
    planner = InstallationPlanner()
    intents = [
        Intent("install", "cuda"),
        Intent("install", "pytorch"),
        Intent("configure", "gpu"),
    ]
    plan = planner.build_plan(intents)

    assert "Install CUDA 12.3 + drivers" in plan
    assert "Install PyTorch (GPU support)" in plan
    assert "Configure GPU acceleration environment" in plan
    assert plan[-1] == "Verify installation and GPU acceleration"
