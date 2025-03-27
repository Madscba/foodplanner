with source as (

    select * from {{ source('foodplanner', 'users_to_preferences') }}

)



select * from source 
