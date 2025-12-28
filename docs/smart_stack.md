# Smart Stacks

Predefined package groups you can install in one command.

Smart Stacks provide ready-to-use package combinations for Machine Learning, Web Development, DevOps, and Data workflows. Each stack is defined in `stacks.json` and installed via the standard `cortex install` flow.

---

## Usage

```bash
cortex stack --list              # List all stacks
cortex stack --describe ml       # Show stack details
cortex stack ml --dry-run        # Preview packages
cortex stack ml                  # Install stack
```

---

## Available Stacks

### **ml - Machine Learning (GPU or CPU auto-detected)**
- pytorch  
- cuda (if GPU present)  
- jupyter  
- numpy  
- pandas  
- matplotlib  

### **ml-cpu - Machine Learning (CPU only)**
- pytorch-cpu  
- jupyter  
- numpy  
- pandas  

### **webdev - Web Development Tools**
- nodejs  
- npm  
- nginx  
- postgresql  

### **devops - DevOps Tools**
- docker  
- kubectl  
- terraform  
- ansible  

### **data - Data Analysis Tools**
- python3  
- pandas  
- jupyter  
- sqlalchemy  

---

## How It Works

- `cortex stack <name>` calls **StackManager** to load stacks from `stacks.json`.
- For the `ml` stack:
  - Runs `has_nvidia_gpu()` to detect NVIDIA GPU.
  - If GPU is missing → automatically switches to `ml-cpu`.
- Packages are installed using the existing **cortex install** flow.
- `--dry-run` lists packages without installing.

---

## Files

- `cortex/stacks.json` — Stack definitions  
- `cortex/stack_manager.py` — Stack manager class  
- `cortex/cli.py` — CLI command handler  
- `test/test_smart_stacks.py` — Tests for stack loading, GPU detection, and dry-run

---

## Demo Video

Video walkthrough:  
https://drive.google.com/file/d/1WShQDYXhje_RGL1vO_RhGgjcVtuesAEy/view?usp=sharing
---

## Closes

`#252`
