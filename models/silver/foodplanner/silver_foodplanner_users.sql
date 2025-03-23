

with source as (

    select * from {{ source('foodplanner_source', 'users') }}

),

renamed as (

    select
        *
    from source

)

select * from renamed