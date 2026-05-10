# Prerequisites

Before setting up the Fraud Intelligence Platform, ensure your system meets the following requirements.

## System Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| **RAM** | 12 GB | 16 GB | Docker alone needs 8 GB allocated |
| **CPU** | 4 cores | 8 cores | Spark streaming benefits from parallelism |
| **Disk** | 20 GB free | 40 GB free | Docker images + Iceberg data lake |
| **OS** | macOS 13+, Ubuntu 22.04+, Windows 11 (WSL2) | macOS 14+ (Apple Silicon) | Native ARM64 images used where available |

!!! warning "Memory is the primary constraint"
    The full platform runs 16 Docker services. With 16 GB total RAM, allocate **8 GB to Docker Desktop** and leave 8 GB for the host OS. Services are tuned for this budget — do not reduce Docker memory below 8 GB.

## Required Software

### Docker Desktop

Docker Desktop 4.25+ with Docker Compose v2 is required for running the platform.

=== "macOS"

    ```bash
    # Install via Homebrew
    brew install --cask docker

    # Or download from https://www.docker.com/products/docker-desktop/
    ```

=== "Ubuntu/Debian"

    ```bash
    # Install Docker Engine
    sudo apt-get update
    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Add your user to the docker group
    sudo usermod -aG docker $USER
    newgrp docker
    ```

=== "Windows (WSL2)"

    ```powershell
    # Install Docker Desktop for Windows
    # Enable WSL2 backend in Docker Desktop settings
    # Ensure WSL2 integration is enabled for your distro
    winget install Docker.DockerDesktop
    ```

#### Docker Desktop Configuration

Open Docker Desktop **Settings > Resources** and apply:

| Setting | Value |
|---------|-------|
| **Memory** | 8.00 GB |
| **CPUs** | 4 (minimum) |
| **Swap** | 2 GB |
| **Disk image size** | 60 GB |

!!! tip "Apply and restart"
    After changing resource limits, click **Apply & Restart**. Verify with:
    ```bash
    docker info | grep -E "Total Memory|CPUs"
    ```

### Python 3.11+

Python is required for the backend API, ML pipeline, and Airflow DAGs.

=== "macOS"

    ```bash
    brew install python@3.11
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install python3.11 python3.11-venv python3-pip
    ```

**Verify installation:**

```bash
python3 --version
# Expected: Python 3.11.x or higher
```

### Node.js 20+

Node.js is required for building the React frontend dashboard.

=== "macOS"

    ```bash
    brew install node@20
    ```

=== "Ubuntu/Debian"

    ```bash
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
    ```

**Verify installation:**

```bash
node --version
# Expected: v20.x.x or higher

npm --version
# Expected: 10.x.x or higher
```

### Git

=== "macOS"

    ```bash
    # Included with Xcode Command Line Tools
    xcode-select --install
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install git
    ```

**Verify installation:**

```bash
git --version
# Expected: git version 2.39+ 
```

### GNU Make

=== "macOS"

    ```bash
    # Included with Xcode Command Line Tools
    make --version
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install make
    ```

## Optional Software

These tools are not required but enhance the development experience.

| Tool | Purpose | Install |
|------|---------|---------|
| **kubectl** | Kubernetes deployment (optional path) | `brew install kubectl` |
| **helm** | Kubernetes package management | `brew install helm` |
| **k9s** | Kubernetes TUI dashboard | `brew install k9s` |
| **jq** | JSON processing for API debugging | `brew install jq` |
| **httpie** | Human-friendly HTTP client | `brew install httpie` |
| **lazydocker** | Docker TUI dashboard | `brew install lazydocker` |

## Apple Silicon (ARM64) Compatibility

!!! info "Native ARM64 support"
    All services use ARM64-native images on Apple Silicon Macs. No Rosetta emulation is needed for the core platform.

| Service | ARM64 Status | Notes |
|---------|-------------|-------|
| Kafka (KRaft) | Native | `confluentinc/cp-kafka` ARM64 images |
| Spark | Native | `bitnami/spark` multi-arch |
| MinIO | Native | Official ARM64 build |
| PostgreSQL | Native | Official ARM64 build |
| Nessie | Native | JVM-based, architecture-independent |
| Airflow | Native | Official `apache/airflow` ARM64 |
| Redis | Native | Official ARM64 build |
| Ollama | Native | Metal GPU acceleration on M-series |
| ChromaDB | Native | Python-based |
| Prometheus | Native | Official ARM64 build |
| Grafana | Native | Official ARM64 build |

!!! tip "Ollama GPU acceleration"
    On Apple Silicon, Ollama automatically uses Metal for GPU-accelerated inference. The `phi3:mini` model runs significantly faster on M1/M2/M3 compared to CPU-only execution on Intel Macs.

## Verification Checklist

Run these commands to verify all prerequisites are met:

```bash
# Docker
docker --version          # Docker version 24.0+
docker compose version    # Docker Compose version v2.20+

# Python
python3 --version         # Python 3.11+

# Node.js
node --version            # v20+
npm --version             # 10+

# Git
git --version             # git version 2.39+

# Make
make --version            # GNU Make 3.81+
```

Or use the built-in verification script:

```bash
# After cloning the repository
make check-prereqs
```

!!! success "Ready to proceed"
    Once all required tools are installed and Docker Desktop is configured with 8 GB RAM, proceed to the [Quick Start](quick-start.md) guide.

## Next Steps

- [Quick Start Guide](quick-start.md) — Get the platform running in 5 minutes
- [Configuration Reference](configuration.md) — Customize environment variables
