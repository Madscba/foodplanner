with source as (

    select * from {{ source('foodplanner', 'users') }}

)



select * from source