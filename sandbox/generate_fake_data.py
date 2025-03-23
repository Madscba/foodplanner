import pandas as pd
import numpy as np
from faker import Faker
from datetime import datetime, timedelta
import random
import uuid
import glob
import re
import ast

# Set seed for reproducibility
np.random.seed(42)
random.seed(42)
fake = Faker()
Faker.seed(42)

# Current date for reference
CURRENT_DATE = datetime.strptime("2025-03-23", "%Y-%m-%d").date()


# Helper function to generate dates in correct sequence
def generate_date_sequence(start_range, end_range=None, nullable_pct=0):
    """Generate a start date and optionally an end date that comes after it"""
    if isinstance(start_range[0], str):
        start_range = (datetime.strptime(start_range[0], '%Y-%m-%d').date(),
                       datetime.strptime(start_range[1], '%Y-%m-%d').date())

    # Ensure the range is valid (start is before end)
    if start_range[0] > start_range[1]:
        start_range = (start_range[1], start_range[0])

    start_date = fake.date_between_dates(date_start=start_range[0], date_end=start_range[1])

    if end_range is None:
        return start_date, None

    # Chance for NULL end date (still active)
    if nullable_pct > 0 and random.random() < nullable_pct:
        return start_date, None

    if isinstance(end_range[0], str):
        end_range = (datetime.strptime(end_range[0], '%Y-%m-%d').date(),
                     datetime.strptime(end_range[1], '%Y-%m-%d').date())

    # Ensure end date is after start date
    end_date_start = max(start_date, end_range[0])

    # Validate that end_date_start is before end_range[1]
    if end_date_start > end_range[1]:
        end_range = (end_date_start, end_date_start + timedelta(days=30))  # Create a valid future window

    end_date = fake.date_between_dates(date_start=end_date_start, date_end=end_range[1])
    return start_date, end_date


# Load external datasets
try:
    recipe_dataset = pd.read_csv(r"C:\Users\MadsChristianBerggre\Downloads\archive (3)\RAW_recipes.csv")
    files_paths = r"C:\Users\MadsChristianBerggre\Downloads\archive (2)\FINAL FOOD DATASET\*.csv"
    files = glob.glob(files_paths)
    food_nutrition_dataset = []
    for idx, file in enumerate(files):
        temp_dataset = pd.read_csv(file)
        if idx == 0:
            food_nutrition_dataset = temp_dataset
        else:
            food_nutrition_dataset = pd.concat((food_nutrition_dataset, temp_dataset))
except Exception as e:
    print(f"Error loading external datasets: {e}")
    print("Using fallback synthetic data instead...")
    # Create fallback datasets if loading fails
    recipe_dataset = pd.DataFrame({
        'id': range(1, 1001),
        'name': [f"Recipe {i}" for i in range(1, 1001)],
        'steps': [[f"Step {j}" for j in range(1, 6)] for i in range(1, 1001)],
        'ingredients': [[f"Ingredient {j}" for j in range(1, 6)] for i in range(1, 1001)]
    })
    food_nutrition_dataset = pd.DataFrame({
        'food': [f"Food {i}" for i in range(1, 201)],
        'Caloric Value': np.random.uniform(10, 500, 200),
        'Fat': np.random.uniform(0, 30, 200),
        'Protein': np.random.uniform(0, 50, 200),
        'Carbohydrates': np.random.uniform(0, 50, 200)
    })

# Clean and prepare the real datasets
# Process ingredients dataset
df_ingredients = food_nutrition_dataset.copy()
df_ingredients = df_ingredients.drop_duplicates(subset=['food'])  # Remove duplicate foods
df_ingredients['Ingredient_ID'] = [str(uuid.uuid4()) for _ in range(len(df_ingredients))]  # Add UUID
df_ingredients = df_ingredients.rename(columns={
    'food': 'Ingredient_name',
    'Caloric Value': 'Calories',
    'Fat': 'Fat',
    'Protein': 'Protein',
    'Carbohydrates': 'Carbs'
})

# Create a unified nutritional facts string
df_ingredients['Nutritional_facts'] = df_ingredients.apply(
    lambda row: f"Calories: {row.get('Calories', 0):.1f}, " +
                f"Protein: {row.get('Protein', 0):.1f}g, " +
                f"Carbs: {row.get('Carbs', 0):.1f}g, " +
                f"Fat: {row.get('Fat', 0):.1f}g",
    axis=1
)

# Add allergen information based on ingredient name
allergen_map = {
    'peanut': 'Peanuts',
    'milk': 'Dairy', 'cheese': 'Dairy', 'yogurt': 'Dairy', 'cream': 'Dairy', 'butter': 'Dairy',
    'gluten': 'Gluten', 'wheat': 'Gluten', 'barley': 'Gluten', 'rye': 'Gluten',
    'egg': 'Eggs',
    'soy': 'Soy', 'tofu': 'Soy',
    'shrimp': 'Shellfish', 'crab': 'Shellfish', 'lobster': 'Shellfish',
    'almond': 'Tree Nuts', 'cashew': 'Tree Nuts', 'walnut': 'Tree Nuts', 'pecan': 'Tree Nuts'
}


def determine_allergen(ingredient_name):
    name_lower = str(ingredient_name).lower()
    for key, allergen in allergen_map.items():
        if key in name_lower:
            return allergen
    return 'None'


df_ingredients['Allergens'] = df_ingredients['Ingredient_name'].apply(determine_allergen)

# Process recipes dataset
df_recipes = recipe_dataset.copy()
# Use the original recipe id but convert it to string to be consistent with our uuid format
df_recipes['Recipe_ID'] = df_recipes['id'].astype(str)
df_recipes = df_recipes.rename(columns={
    'name': 'Recipe_name',
    'steps': 'Instructions'
})


# Clean up instructions - convert from string representation of list to single text
def clean_instructions(steps_str):
    try:
        if isinstance(steps_str, list):
            return "\n".join([f"{i + 1}. {step}" for i, step in enumerate(steps_str)])
        steps_list = ast.literal_eval(steps_str)
        return "\n".join([f"{i + 1}. {step}" for i, step in enumerate(steps_list)])
    except:
        return str(steps_str)


df_recipes['Instructions'] = df_recipes['Instructions'].apply(clean_instructions)

# Store the recipe IDs for later use
recipe_ids = df_recipes['Recipe_ID'].tolist()
ingredient_ids = df_ingredients['Ingredient_ID'].tolist()

# Extract recipe ingredients from the original dataset
recipe_ingredient_rows = []

# Parse ingredients from recipe_dataset
for idx, row in df_recipes.iterrows():
    try:
        recipe_id = row['Recipe_ID']
        # Get original row from recipe_dataset
        original_row = recipe_dataset[recipe_dataset['id'] == int(recipe_id)]
        if not original_row.empty:
            ingredients_str = original_row['ingredients'].iloc[0]

            # Handle various input formats
            if isinstance(ingredients_str, list):
                ingredients_list = ingredients_str
            else:
                try:
                    ingredients_list = ast.literal_eval(ingredients_str)
                except:
                    ingredients_list = [str(ingredients_str)]

            # Assign 3-8 ingredients from our ingredients table to each recipe
            num_ingredients = min(len(ingredients_list), random.randint(3, 8))
            selected_ingredients = random.sample(ingredient_ids, min(num_ingredients, len(ingredient_ids)))

            for i, ingredient_id in enumerate(selected_ingredients):
                recipe_ingredient_rows.append({
                    'Recipe_ID': recipe_id,
                    'Ingredient_ID': ingredient_id,
                    'Quantity': random.randint(1, 5),
                    'Unit': random.choice(['cup', 'tbsp', 'tsp', 'g', 'kg', 'ml', 'l', 'piece'])
                })
    except (ValueError, SyntaxError, IndexError) as e:
        # Skip recipes with parsing issues
        continue

df_recipe_ingredients = pd.DataFrame(recipe_ingredient_rows)

# 1. Users Table
n_users = 10000
user_ids = [str(uuid.uuid4()) for _ in range(n_users)]
# User create dates: between 10 years ago and today
created_dates = [fake.date_between_dates(
    date_start=CURRENT_DATE - timedelta(days=3650),
    date_end=CURRENT_DATE
) for _ in range(n_users)]

active_subscriptions = np.random.choice([True, False], n_users, p=[0.7, 0.3])  # 70% have active subscriptions

df_users = pd.DataFrame({
    'Customer_ID': user_ids,
    'Name': [fake.name() for _ in range(n_users)],
    'Email': [fake.email() for _ in range(n_users)],
    'Address': [fake.address() for _ in range(n_users)],
    'Active_subscription': active_subscriptions,
    'Created_at': created_dates,
})

# Only 10% of users have deletion dates, and they must be after creation
deletion_dates = []
for idx, created_date in enumerate(created_dates):
    if random.random() < 0.1:
        # Set a valid deletion date between creation and today
        if created_date < CURRENT_DATE:
            deletion_dates.append(fake.date_between_dates(
                date_start=created_date,
                date_end=CURRENT_DATE
            ))
        else:
            deletion_dates.append(None)  # Can't delete an account before it's created
    else:
        deletion_dates.append(None)

df_users['Deleted_at'] = deletion_dates

# 2. Preferences Table - Now independent of users
# Define common preference types
preference_types = ['Vegan', 'Vegetarian', 'Gluten-Free', 'Low-Carb', 'Keto', 'Paleo',
                    'Dairy-Free', 'Nut-Free', 'Pescatarian', 'High-Protein', 'Low-Fat',
                    'Mediterranean', 'DASH', 'Organic', 'Non-GMO', 'Local-Sourced']

# Define common value levels
value_levels = ['High', 'Medium', 'Low', 'None']

# Create standard preference descriptions
preference_descriptions = {
    'Vegan': 'Excludes all animal products and by-products.',
    'Vegetarian': 'Excludes meat but allows dairy and eggs.',
    'Gluten-Free': 'Excludes wheat, barley, rye and their derivatives.',
    'Low-Carb': 'Limits carbohydrate intake to focus on proteins and fats.',
    'Keto': 'Very low carb, high fat diet to induce ketosis.',
    'Paleo': 'Based on foods presumed to be available to paleolithic humans.',
    'Dairy-Free': 'Excludes milk and dairy products.',
    'Nut-Free': 'Excludes all tree nuts and peanuts due to allergy concerns.',
    'Pescatarian': 'Vegetarian diet that includes fish and seafood.',
    'High-Protein': 'Focus on increased protein intake for muscle development.',
    'Low-Fat': 'Limits fat intake, especially saturated fats.',
    'Mediterranean': 'Based on traditional cuisines of Mediterranean countries.',
    'DASH': 'Dietary Approach to Stop Hypertension, focusing on heart health.',
    'Organic': 'Preference for organic, pesticide-free ingredients.',
    'Non-GMO': 'Avoids genetically modified organisms in food.',
    'Local-Sourced': 'Preference for locally produced ingredients.'
}

# Create preferences table
n_preferences = len(preference_types)
preference_ids = [str(uuid.uuid4()) for _ in range(n_preferences)]

df_preferences = pd.DataFrame({
    'Preference_ID': preference_ids,
    'Description': [preference_descriptions.get(pref_type, fake.sentence()) for pref_type in preference_types],
    'Type': preference_types,
    'Value': [random.choice(value_levels) for _ in range(n_preferences)]
})

# 3. Create new User_Preferences junction table
user_preference_rows = []

for user_id in user_ids:
    # Each user can have 0-4 preferences
    num_prefs = random.randint(0, 4)
    if num_prefs > 0:
        # Get user's creation date
        user_created_date = df_users[df_users['Customer_ID'] == user_id]['Created_at'].iloc[0]
        user_deleted_date = df_users[df_users['Customer_ID'] == user_id]['Deleted_at'].iloc[0]

        # Select random preferences for this user (no duplicates)
        selected_prefs = random.sample(preference_ids, min(num_prefs, len(preference_ids)))

        for pref_id in selected_prefs:
            # Preferences start sometime after user creation
            # Ensure created_date is not in the future
            created_date_safe = min(user_created_date, CURRENT_DATE)
            pref_start_date = fake.date_between_dates(
                date_start=created_date_safe,
                date_end=CURRENT_DATE
            )

            # 70% chance preference is still active, 30% chance it ended
            if random.random() < 0.7 and pd.isna(user_deleted_date):
                pref_end_date = None
            else:
                # If user is deleted, preference must end on or before deletion date
                end_limit = user_deleted_date if pd.notna(user_deleted_date) else CURRENT_DATE

                # Ensure start_date is before end_limit
                if pref_start_date < end_limit:
                    pref_end_date = fake.date_between_dates(
                        date_start=pref_start_date,
                        date_end=end_limit
                    )
                else:
                    # If start date is somehow after end limit, just use the start date for end date
                    pref_end_date = pref_start_date

            user_preference_rows.append({
                'Customer_ID': user_id,
                'Preference_ID': pref_id,
                'Start_date': pref_start_date,
                'End_date': pref_end_date
            })

df_user_preferences = pd.DataFrame(user_preference_rows)

# 4. Subscriptions Table - Only for users with active subscriptions
subscription_rows = []
subscription_ids = []
subscription_to_user = {}  # Keep track of which subscription belongs to which user

users_with_active_sub = df_users[df_users['Active_subscription'] == True]['Customer_ID'].tolist()
users_without_active_sub = df_users[df_users['Active_subscription'] == False]['Customer_ID'].tolist()

# Active subscriptions
for user_id in users_with_active_sub:
    user_created_date = df_users[df_users['Customer_ID'] == user_id]['Created_at'].iloc[0]
    sub_id = str(uuid.uuid4())

    # Ensure user_created_date is not in the future
    created_date_safe = min(user_created_date, CURRENT_DATE)
    start_date = fake.date_between_dates(
        date_start=created_date_safe,
        date_end=CURRENT_DATE
    )

    subscription_rows.append({
        'Subscription_ID': sub_id,
        'Customer_ID': user_id,
        'Create_date': start_date,
        'End_date': None,  # Active subscription has no end date
        'Subscription_plan': random.choice(['Basic', 'Premium', 'Family'])
    })
    subscription_ids.append(sub_id)
    subscription_to_user[sub_id] = user_id

# Past subscriptions (for both active and inactive users)
for user_id in user_ids:
    # Determine how many past subscriptions this user had (0-2)
    num_past_subs = random.randint(0, 2)

    if num_past_subs > 0:
        user_created_date = df_users[df_users['Customer_ID'] == user_id]['Created_at'].iloc[0]

        # Ensure user_created_date is not in the future
        created_date_safe = min(user_created_date, CURRENT_DATE)

        for _ in range(num_past_subs):
            sub_id = str(uuid.uuid4())
            start_date = fake.date_between_dates(
                date_start=created_date_safe,
                date_end=CURRENT_DATE
            )
            end_date = fake.date_between_dates(
                date_start=start_date,
                date_end=CURRENT_DATE
            )

            subscription_rows.append({
                'Subscription_ID': sub_id,
                'Customer_ID': user_id,
                'Create_date': start_date,
                'End_date': end_date,
                'Subscription_plan': random.choice(['Basic', 'Premium', 'Family'])
            })
            subscription_ids.append(sub_id)
            subscription_to_user[sub_id] = user_id

df_subscriptions = pd.DataFrame(subscription_rows)

# 5. Payments Table - Monthly payments only for active subscriptions
payment_rows = []

for idx, row in df_subscriptions.iterrows():
    sub_id = row['Subscription_ID']
    start_date = row['Create_date']
    end_date = row['End_date'] if pd.notna(row['End_date']) else CURRENT_DATE

    # Calculate number of months this subscription was/is active
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    # Determine subscription price based on plan
    if row['Subscription_plan'] == 'Basic':
        amount = random.uniform(9.99, 14.99)
    elif row['Subscription_plan'] == 'Premium':
        amount = random.uniform(19.99, 29.99)
    else:  # Family plan
        amount = random.uniform(29.99, 49.99)

    # Generate monthly payments
    current_date = start_date
    while current_date <= end_date:
        due_date = current_date

        # 90% chance payment is made on time, 10% chance it's late
        if random.random() < 0.9:
            pay_date = due_date - timedelta(days=random.randint(0, 5))
            status = 'Paid'
        else:
            pay_date = due_date + timedelta(days=random.randint(1, 10))
            status = 'Late'

        payment_rows.append({
            'Payment_ID': str(uuid.uuid4()),
            'Subscription_ID': sub_id,
            'Description': f"Monthly payment for {row['Subscription_plan']} plan",
            'Due_date': due_date,
            'Pay_date': pay_date,
            'Amount': round(amount, 2),
            'Status': status
        })

        # Move to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            # Try to set next month, handling edge cases like Jan 31 -> Feb 28
            try:
                current_date = current_date.replace(month=current_date.month + 1)
            except ValueError:
                # Handle edge case (e.g., Jan 31 -> Feb 28)
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1, day=1)

df_payments = pd.DataFrame(payment_rows)

# 6. Foodplans Table - Only for active subscriptions
foodplan_rows = []
foodplan_ids = []

active_subs = df_subscriptions[df_subscriptions['End_date'].isna()]['Subscription_ID'].tolist()
for sub_id in active_subs:
    if sub_id in subscription_to_user:
        user_id = subscription_to_user[sub_id]

        # Each active subscription may have 1-3 food plans
        num_foodplans = random.randint(1, 3)

        for _ in range(num_foodplans):
            foodplan_id = str(uuid.uuid4())
            sub_start_date = df_subscriptions[df_subscriptions['Subscription_ID'] == sub_id]['Create_date'].iloc[0]

            if isinstance(sub_start_date, str):
                sub_start_date = datetime.strptime(sub_start_date, '%Y-%m-%d').date()

            # Ensure sub_start_date is not in the future
            sub_start_date_safe = min(sub_start_date, CURRENT_DATE)

            plan_start = fake.date_between_dates(
                date_start=sub_start_date_safe,
                date_end=CURRENT_DATE
            )

            # Plan end date is between start date and 90 days after start
            plan_end_limit = min(plan_start + timedelta(days=90), CURRENT_DATE)
            plan_end = fake.date_between_dates(
                date_start=plan_start,
                date_end=plan_end_limit
            )

            # Use the user's actual preferences if they have any
            user_active_prefs = df_user_preferences[
                (df_user_preferences['Customer_ID'] == user_id) &
                (df_user_preferences['End_date'].isna())
                ]

            if len(user_active_prefs) > 0:
                pref_id = user_active_prefs.sample(1)['Preference_ID'].iloc[0]
                pref_type = df_preferences[df_preferences['Preference_ID'] == pref_id]['Type'].iloc[0]
                preference = pref_type
            else:
                preference = random.choice(
                    ['Vegetarian', 'Low-Carb', 'High-Protein', 'Vegan', 'Gluten-Free', 'Balanced'])

            foodplan_rows.append({
                'Foodplan_ID': foodplan_id,
                'Customer_ID': user_id,
                'Subscription_ID': sub_id,
                'Start_date': plan_start,
                'End_date': plan_end,
                'Preferences': preference,
                'Nutrition': random.choice(['Balanced', 'High Protein', 'Low Sugar', 'Low Fat', 'Low Sodium'])
            })
            foodplan_ids.append(foodplan_id)

df_foodplans = pd.DataFrame(foodplan_rows)

# 7. Retail Magazines Table - Weekly magazines with valid dates
n_magazines = 52  # One year of weekly magazines
magazine_rows = []
magazine_ids = []

# Start 6 months ago and go forward
magazine_start_date = CURRENT_DATE - timedelta(days=180)
for i in range(n_magazines):
    magazine_id = str(uuid.uuid4())
    valid_from = magazine_start_date + timedelta(days=i * 7)
    end_date = valid_from + timedelta(days=6)  # Valid for one week

    magazine_rows.append({
        'Magazine_ID': magazine_id,
        'Valid_from_date': valid_from,
        'End_date': end_date,
        'Title': f"Weekly Specials {valid_from.strftime('%Y-%m-%d')}"
    })
    magazine_ids.append(magazine_id)

df_magazines = pd.DataFrame(magazine_rows)

# 8. Magazine_Ingredients Table - Each magazine features 20-50 ingredients
magazine_ingredient_rows = []
for magazine_id in magazine_ids:
    num_ingredients = random.randint(20, 50)
    selected_ingredients = random.sample(ingredient_ids, min(num_ingredients, len(ingredient_ids)))

    for ingredient_id in selected_ingredients:
        original_price = round(random.uniform(1, 20), 2)
        discount_pct = random.uniform(0.05, 0.4)  # 5-40% discount
        discount = round(original_price * discount_pct, 2)

        magazine_ingredient_rows.append({
            'Magazine_ID': magazine_id,
            'Ingredient_ID': ingredient_id,
            'Original_price': original_price,
            'Discount': discount,
            'Final_price': round(original_price - discount, 2)  # Added for convenience
        })

df_magazine_ingredients = pd.DataFrame(magazine_ingredient_rows)

# 9. Foodplan_Recipes Table - Each foodplan includes 5-14 recipes
foodplan_recipe_rows = []
for foodplan_id in foodplan_ids:
    num_recipes = random.randint(5, 14)
    selected_recipes = random.sample(recipe_ids, min(num_recipes, len(recipe_ids)))

    for i, recipe_id in enumerate(selected_recipes):
        foodplan_recipe_rows.append({
            'Foodplan_ID': foodplan_id,
            'Recipe_ID': recipe_id,
            'Day_number': i + 1,  # Assign each recipe to a day in the plan
            'Meal_type': random.choice(['Breakfast', 'Lunch', 'Dinner', 'Snack'])
        })

df_foodplan_recipes = pd.DataFrame(foodplan_recipe_rows)


#Fix loading error in Snowflake
df_recipes['Instructions'] = df_recipes['Instructions'].astype(str)
df_recipes['Instructions'] = df_recipes['Instructions'].apply(lambda x: f'"{x}"')
df_recipes = df_recipes.drop("description", axis=1)

# Save all datasets to CSV
df_users.to_csv("users.csv", index=False)
df_preferences.to_csv("preferences.csv", index=False)
df_user_preferences.to_csv("user_preferences.csv", index=False)
df_subscriptions.to_csv("subscriptions.csv", index=False)
df_payments.to_csv("payments.csv", index=False)
df_foodplans.to_csv("foodplans.csv", index=False)
df_recipes.to_csv("recipes.csv", index=False)
df_recipe_ingredients.to_csv("recipe_ingredients.csv", index=False)
df_ingredients.to_csv("ingredients.csv", index=False)
df_magazines.to_csv("magazines.csv", index=False)
df_magazine_ingredients.to_csv("magazine_ingredients.csv", index=False)
df_foodplan_recipes.to_csv("foodplan_recipes.csv", index=False)

print("Successfully generated consistent fake data with improved user preferences structure!")