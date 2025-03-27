with source as (

    select * from {{ source('foodplanner', 'magazines') }}

),

renamed as (

    select
        *
    from source

)

select * from source