with source as (

    select * from {{ source('foodplanner', 'subscriptions') }}

)



select * from source