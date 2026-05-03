from datetime import datetime

print("METRICS LOADED FROM:", __file__)

# calculate users current bmi
def calculate_bmi(weight_lbs: float, height_in: float) -> float:
    return round((weight_lbs * 703) / (height_in **2), 2)

# calculate users target bmi
def calculate_goal_bmi(goal_weight_lbs: float, height_in: float) -> float:
    return round((goal_weight_lbs * 703) / (height_in **2), 2)


def calculate_age(birthday: str) -> int:
    birth_date = datetime.strptime(birthday, "%Y-%m-%d")
    today = datetime.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age