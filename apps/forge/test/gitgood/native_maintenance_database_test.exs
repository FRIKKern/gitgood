defmodule Gitgood.NativeMaintenanceDatabaseTest do
  use Gitgood.DataCase, async: false
  alias Gitgood.NativeMaintenanceWorker, as: Worker

  defp versions,
    do:
      Repo.query!("SELECT version FROM public.schema_migrations ORDER BY version", []).rows
      |> List.flatten()

  test "migration and bootstrap compare actual schema without changing it" do
    actual = versions()
    assert actual != []
    assert :ok = Worker.validate_database(:migrate, %{"before_versions" => actual})
    assert :ok = Worker.validate_database(:bootstrap, %{"target_versions" => actual})

    for expected <- [[], Enum.drop(actual, 1), actual ++ [List.last(actual) + 1]] do
      assert :error = Worker.validate_database(:migrate, %{"before_versions" => expected})
      assert :error = Worker.validate_database(:bootstrap, %{"target_versions" => expected})
      assert versions() == actual
    end
  end

  test "empty migration history cannot disguise an existing application schema" do
    Repo.query!("DELETE FROM public.schema_migrations", [])
    assert versions() == []
    assert :error = Worker.validate_database(:migrate, %{"before_versions" => []})
    assert versions() == []
    assert Repo.query!("SELECT to_regclass('public.users') IS NOT NULL", []).rows == [[true]]
  end

  test "missing migration table also refuses an existing application schema" do
    Repo.query!("DROP TABLE public.schema_migrations", [])
    assert :error = Worker.validate_database(:migrate, %{"before_versions" => []})
    assert :error = Worker.validate_database(:bootstrap, %{"target_versions" => [1]})

    assert Repo.query!("SELECT to_regclass('public.schema_migrations') IS NULL", []).rows == [
             [true]
           ]
  end
end
