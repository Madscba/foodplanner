with source as (

    select * from {{ source('foodplanner', 'payments') }}

)


select * from source