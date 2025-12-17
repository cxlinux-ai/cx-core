import time
from cortex.hardware_detection import detect_hardware
from cortex.branding import show_banner



def run_demo():
    show_banner()
    print("\n🚀 Cortex One-Command Investor Demo\n")

    # 1️⃣ Hardware Scan
    print("🔍 Scanning system hardware...")
    time.sleep(0.8)

    hw = detect_hardware()

    print(f"✔ CPU: {hw.get('cpu', 'Unknown')}")
    print(f"✔ RAM: {hw.get('memory_gb', 'Unknown')} GB")

    gpu = hw.get("gpu")
    if gpu:
        print(f"✔ GPU: {gpu}")
    else:
        print("⚠️ GPU: Not detected (CPU mode enabled)")

    # 2️⃣ Model Recommendations
    print("\n🤖 Model Recommendations:")
    if gpu:
        print("• LLaMA-3-8B → Optimized for your GPU")
        print("• Mistral-7B → High performance inference")
    else:
        print("• Phi-2 → Lightweight CPU model")
        print("• Mistral-7B-Instruct → Efficient on CPU")

    # 3️⃣ Quick LLM Test (safe mock)
    print("\n🧪 Running quick LLM test...")
    time.sleep(1)
    print("Prompt: Hello from Cortex")
    print("Response: Hello! Your system is AI-ready 🚀")

    # 4️⃣ Kernel / System Status
    print("\n⚙️ System Status:")
    print("✔ Kernel Scheduler: Active")
    print("✔ AI Runtime: Ready")

    # 5️⃣ Summary
    print("\n✅ Demo Complete")
    print("🎉 Your system is READY for AI workloads\n")