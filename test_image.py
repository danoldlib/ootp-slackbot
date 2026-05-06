import os
from dotenv import load_dotenv
from bot import generate_player_image

load_dotenv()

if __name__ == "__main__":
    print("Testing Image Generation with Gemini...")
    
    # Test a Batter
    print("\n1. Generating Batter Image (Mario Ramirez, ARI)...")
    batter_img = generate_player_image("Mario Ramirez", "ARI", is_pitcher=False)
    if batter_img:
        print(f"Success! Image saved to: {batter_img}")
        
    # Test a Pitcher
    print("\n2. Generating Pitcher Image (Brett Myers, PHI)...")
    pitcher_img = generate_player_image("Brett Myers", "PHI", is_pitcher=True)
    if pitcher_img:
        print(f"Success! Image saved to: {pitcher_img}")
        
    print("\nCheck your current directory to view the .jpg files!")
