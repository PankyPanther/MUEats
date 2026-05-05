from auth import create_user, login, get_user_profile
from db import get_db
from updates import update_user_stats
from meals import create_meal, get_user_meals
from analytics import get_weekly_summary

def main():
    print("Creating user ...")
    create_user("drufrazier", "fraziead@miamioh.edu", "password123",
                height = 73, weight = 160, birthday = 5/21/2005, goal_weight = 180) # should succeed

    print("\n logging in ...")
    login("fraziead@miamioh.edu", "password123") # should succeed

    print("\n getting user profile ...")
    profile = get_user_profile("fraziead@miamioh.edu")
    print(profile)

    print("\n updating user stats ...")
    update_user_stats("fraziead@miamioh.edu", new_height=74, new_weight=158)
    print(profile)

    print("\nLogging a meal ...")
    create_meal("fraziead@miamioh.edu", "Breakfast", ["Oatmeal", "Banana"], 350)
    print("\nGetting user meals ...")
    user_meals = get_user_meals("fraziead@miamioh.edu")
    print(user_meals)


if __name__ == "__main__":
    main()



