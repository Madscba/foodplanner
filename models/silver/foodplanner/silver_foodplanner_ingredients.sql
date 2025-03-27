with source as (

    select * from {{ source('foodplanner', 'ingredients') }}

),

renamed as (

    select
        *
    from source

)

select * from source