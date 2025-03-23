USE DATABASE BRONZE;
USE SCHEMA FOODPLANNER_RAW;

WITH source AS (
    SELECT * FROM {{ source('foodplanner_source', 'users_to_preferences') }}
),

renamed AS (
    SELECT * FROM source
)

SELECT * FROM renamed;