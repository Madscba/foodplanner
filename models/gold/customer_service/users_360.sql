{{ config(materialized='table', sort='Customer_ID') }}

WITH all_user_details AS (
    SELECT 
        u.Customer_ID,
        u.Name,
        u.Email,
        u.Address,
        u.Active_subscription,
        s.Subscription_ID,
        s.Create_date AS Subscription_Start_Date,
        s.End_date AS Subscription_End_Date,
        s.Subscription_plan,
        p.Payment_ID,
        p.Description AS Payment_Description,
        p.Due_date AS Payment_Due_Date,
        p.Pay_date AS Payment_Paid_Date,
        p.Amount AS Payment_Amount,
        p.Status AS Payment_Status,
        pr.Preference_ID,
        pr.Type AS Preference_Type,
        pr.Value AS Preference_Value,
        fp.Foodplan_ID,
        fp.Start_date AS Foodplan_Start_Date,
        fp.End_date AS Foodplan_End_Date,
        fp.Preferences AS Foodplan_Preferences,
        fp.Nutrition AS Foodplan_Nutrition,
        r.Recipe_ID,
        r.Recipe_name
    FROM {{ ref("silver_foodplanner_users")}} u
        LEFT JOIN {{ ref("silver_foodplanner_subscriptions")}} s ON u.Customer_ID = s.Customer_ID
        LEFT JOIN {{ ref("silver_foodplanner_payments")}} p ON s.Subscription_ID = p.Subscription_ID
        LEFT JOIN {{ ref("silver_foodplanner_users_to_preferences")}} us_pr ON u.Customer_ID = us_pr.Customer_ID
        LEFT JOIN {{ ref("silver_foodplanner_dietary_preferences")}} pr ON us_pr.Preference_ID = pr.Preference_ID
        LEFT JOIN {{ ref("silver_foodplanner_foodplans")}} fp ON u.Customer_ID = fp.Customer_ID
        LEFT JOIN {{ ref("silver_foodplanner_foodplan_recipes")}} fr ON fp.Foodplan_ID = fr.Foodplan_ID
        LEFT JOIN {{ ref("silver_foodplanner_recipes")}} r ON fr.Recipe_ID = r.Recipe_ID
    ORDER BY u.Customer_ID, s.Subscription_ID, p.Payment_ID
    ),

latest_subscriptions AS (
    SELECT 
        Customer_ID,
        Subscription_ID,
        Subscription_Start_Date,
        Subscription_End_Date,
        Subscription_plan,
        ROW_NUMBER() OVER (PARTITION BY Customer_ID ORDER BY Subscription_Start_Date DESC, Subscription_ID DESC) AS rn
    FROM all_user_details
    WHERE Subscription_ID IS NOT NULL
),

latest_payments AS (
    SELECT 
        Customer_ID,
        Payment_ID,
        Payment_Description,
        Payment_Due_Date,
        Payment_Paid_Date,
        Payment_Amount,
        Payment_Status,
        ROW_NUMBER() OVER (PARTITION BY Customer_ID ORDER BY Payment_Due_Date DESC, Payment_ID DESC) AS rn
    FROM all_user_details
    WHERE Payment_ID IS NOT NULL
),

latest_foodplans AS (
    SELECT 
        Customer_ID,
        Foodplan_ID,
        Foodplan_Start_Date,
        Foodplan_End_Date,
        Foodplan_Preferences,
        Foodplan_Nutrition,
        ROW_NUMBER() OVER (PARTITION BY Customer_ID ORDER BY Foodplan_Start_Date DESC, Foodplan_ID DESC) AS rn
    FROM all_user_details
    WHERE Foodplan_ID IS NOT NULL
)

SELECT 
    ud.Customer_ID,
    MAX(ud.Name) AS Name,
    MAX(ud.Email) AS Email,
    MAX(ud.Address) AS Address,
    MAX(ud.Active_subscription) AS Active_subscription,
    
    -- Latest Subscription Details
    MAX(ls.Subscription_ID) AS Subscription_ID,
    MAX(ls.Subscription_Start_Date) AS Subscription_Start_Date,
    MAX(ls.Subscription_End_Date) AS Subscription_End_Date,
    MAX(ls.Subscription_plan) AS Subscription_plan,
    
    -- Latest Payment Details
    MAX(lp.Payment_ID) AS Payment_ID,
    MAX(lp.Payment_Description) AS Payment_Description,
    MAX(lp.Payment_Due_Date) AS Payment_Due_Date,
    MAX(lp.Payment_Paid_Date) AS Payment_Paid_Date,
    MAX(lp.Payment_Amount) AS Payment_Amount,
    MAX(lp.Payment_Status) AS Payment_Status,
    
    -- Preferences as an array
    ARRAY_AGG(DISTINCT OBJECT_CONSTRUCT('id', ud.Preference_ID, 'type', ud.Preference_Type, 'value', ud.Preference_Value)) 
         AS Preferences,
    
    -- Latest Food Plan Details
    MAX(lf.Foodplan_ID) AS Foodplan_ID,
    MAX(lf.Foodplan_Start_Date) AS Foodplan_Start_Date,
    MAX(lf.Foodplan_End_Date) AS Foodplan_End_Date,
    MAX(lf.Foodplan_Preferences) AS Foodplan_Preferences,
    MAX(lf.Foodplan_Nutrition) AS Foodplan_Nutrition,
    
    -- Count of Recipes
    COUNT(DISTINCT ud.Recipe_ID) AS Recipe_Count
    
FROM all_user_details ud
LEFT JOIN latest_subscriptions ls ON ud.Customer_ID = ls.Customer_ID AND ls.rn = 1
LEFT JOIN latest_payments lp ON ud.Customer_ID = lp.Customer_ID AND lp.rn = 1
LEFT JOIN latest_foodplans lf ON ud.Customer_ID = lf.Customer_ID AND lf.rn = 1
GROUP BY ud.Customer_ID
ORDER BY ud.Customer_ID