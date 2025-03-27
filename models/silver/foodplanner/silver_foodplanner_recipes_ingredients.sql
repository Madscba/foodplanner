with source as (

    select * from {{ source('foodplanner', 'recipe_ingredients') }}

),

renamed as (

    select
        *
    from source

)

select * from source