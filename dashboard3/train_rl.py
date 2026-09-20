#!/usr/bin/env python3
"""
Training script for enhanced RL controller
"""

import os, sys
import numpy as np
import matplotlib.pyplot as plt
from enhanced_rl_controller import train_rl_controller

def run_training_episodes(num_episodes=5):
    """Run multiple training episodes"""
    print(f"🎯 Starting {num_episodes} training episodes")
    
    episode_rewards = []
    episode_steps = []
    
    for episode in range(num_episodes):
        print(f"\n📈 Episode {episode + 1}/{num_episodes}")
        
        # Run training
        try:
            train_rl_controller()
            print(f"✅ Episode {episode + 1} completed")
        except Exception as e:
            print(f"❌ Episode {episode + 1} failed: {e}")
            continue
    
    print(f"\n🏁 Training completed: {num_episodes} episodes")

if __name__ == "__main__":
    run_training_episodes()