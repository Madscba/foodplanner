with source as (

    select * from {{ source('foodplanner', 'recipes') }}

),

renamed as (

    select
        *
    from source

)

select * from renamed