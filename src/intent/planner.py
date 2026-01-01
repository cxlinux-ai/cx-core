from intent.detector import Intent

# planner.py


class InstallationPlanner:
    GPU_PACKAGES = ["cuda", "cudnn", "pytorch", "tensorflow"]

    def build_plan(self, intents: list[Intent]) -> list[str]:
        plan = []
        installed = set()

        # 1. If GPU-related intents exist → add GPU detection
        has_gpu = any(i.target == "gpu" for i in intents)
        if has_gpu:
            plan.append("Detect GPU: Run `nvidia-smi` or PCI scan")

        # 2. Add installation steps based on intent order
        for intent in intents:
            if intent.action == "install" and intent.target not in installed:
                if intent.target == "cuda":
                    plan.append("Install CUDA 12.3 + drivers")

                elif intent.target == "cudnn":
                    plan.append("Install cuDNN (matching CUDA version)")

                elif intent.target == "pytorch":
                    plan.append("Install PyTorch (GPU support)")

                elif intent.target == "tensorflow":
                    plan.append("Install TensorFlow (GPU support)")

                elif intent.target == "jupyter":
                    plan.append("Install JupyterLab")

                elif intent.target == "gpu":
                    # GPU setup is handled by CUDA/cuDNN
                    pass

                installed.add(intent.target)

        # 3. Add GPU configuration if needed
        if has_gpu:
            plan.append("Configure GPU acceleration environment")

        # 4. Add verification step
        plan.append("Verify installation and GPU acceleration")

        return plan
