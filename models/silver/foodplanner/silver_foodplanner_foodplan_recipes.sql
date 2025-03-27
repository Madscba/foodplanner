with source as (

    select * from {{ source('foodplanner', 'foodplan_recipes') }}

),

renamed as (

    select
        *
    from source

)

select * from renamed

