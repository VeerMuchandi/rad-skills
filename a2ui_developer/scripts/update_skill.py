#!/usr/bin/env python3
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Global A2UI Skill Self-Update Script

This script synchronizes the A2UI skill resources with the official reference repository.
It ensures that the skill, now located globally, stays up-to-date regardless of the current workspace.

Logic:
1.  Defines a global cache directory: `~/.gemini/jetski/cache/repos/a2ui`.
2.  Clones the official A2UI repo (https://github.com/google/A2UI) if not present.
3.  Pulls the latest changes if present.
4.  Synchronizes key directories into the skill folder.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
USER_HOME = Path.home()
CACHE_ROOT = USER_HOME / ".gemini" / "jetski" / "cache" / "repos"
REPO_CACHE_PATH = CACHE_ROOT / "a2ui"
OFFICIAL_REPO_URL = "https://github.com/google/A2UI.git"

DIRECTORIES_TO_SYNC = [
    "specification",
    "docs",
    "renderers",
    "tools",
]

SAMPLES_MAPPING = {
    "samples/agent/adk/rizzcharts": "examples/agent/rizzcharts",
    "samples/agent/adk/contact_lookup": "examples/agent/contact_lookup",
    "samples/client/lit/shell": "examples/client/generic_shell",
}

def log(msg):
    print(f"[A2UI Global Update] {msg}")

def run_command(cmd, cwd=None):
    try:
        subprocess.check_call(cmd, shell=True, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError as e:
        log(f"Command failed: {cmd}")
        return False

def ensure_repo_updated():
    if not REPO_CACHE_PATH.exists():
        log(f"Repo cache not found. Cloning from {OFFICIAL_REPO_URL} to {REPO_CACHE_PATH}...")
        REPO_CACHE_PATH.mkdir(parents=True, exist_ok=True)
        if run_command(f"git clone {OFFICIAL_REPO_URL} .", cwd=REPO_CACHE_PATH):
            log("Cloning successful.")
            return True
        else:
            log("Cloning failed. Please check your internet connection or git configuration.")
            # Verify if maybe we can't clone, is there a fallback? 
            # If cloning fails, we might just have to abort or ask user to provide path.
            return False
    else:
        log(f"Repo cache found at {REPO_CACHE_PATH}. Pulling latest changes...")
        if run_command("git pull", cwd=REPO_CACHE_PATH):
            log("Git pull successful.")
            return True
        else:
            log("Git pull failed. Attempting to proceed with existing cache.")
            return True

def sync_directory(src_rel, dest_rel, exclude_node_modules=True):
    src = REPO_CACHE_PATH / src_rel
    dest = SKILL_ROOT / dest_rel
    
    if not src.exists():
        log(f"Warning: Source {src} does not exist in repo. Skipping.")
        return

    log(f"Syncing {src_rel} -> {dest_rel}...")
    
    if dest.exists():
        shutil.rmtree(dest)
    
    ignore = shutil.ignore_patterns("node_modules", ".git", "__pycache__", ".DS_Store") if exclude_node_modules else None
    shutil.copytree(src, dest, ignore=ignore)

def main():
    log("Starting Global A2UI Skill Self-Update...")
    log(f"Skill Root: {SKILL_ROOT}")
    
    if not ensure_repo_updated():
        log("Critical Error: Could not update reference repository. Aborting sync.")
        sys.exit(1)
    
    # Sync Directories
    for d in DIRECTORIES_TO_SYNC:
        sync_directory(d, d)
        
    # Sync Samples
    for src_rel, dest_rel in SAMPLES_MAPPING.items():
        sync_directory(src_rel, dest_rel)

    log("Global Update complete. Skill is synchronized.")

if __name__ == "__main__":
    main()
