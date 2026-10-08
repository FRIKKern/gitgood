[
  import_deps: [:ecto, :ecto_sql, :phoenix],
  subdirectories: ["priv/*/migrations"],
  inputs: ["*.{ex,exs}", "{config,lib,test,verification}/**/*.{ex,exs}", "priv/*/seeds.exs"]
]
