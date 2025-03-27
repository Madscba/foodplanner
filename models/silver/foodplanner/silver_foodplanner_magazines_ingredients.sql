with source as (

    select * from {{ source('foodplanner', 'magazine_ingredients') }}

),

renamed as (

    select
        *
    from source

)

select * from source