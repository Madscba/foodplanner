with source as (

    select * from {{ source('foodplanner', 'foodplans') }}

),

renamed as (

    select
        *
    from source

)

select * from renamed