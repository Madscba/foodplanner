with source as (

    select * from {{ source('foodplanner', 'dietary_preferences') }}

),

renamed as (

    select
        *
    from source

)

select * from renamed