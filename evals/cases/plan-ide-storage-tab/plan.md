# Plan: storage DDL tab in the IDE demo

## Goal

Let the IDE demo show the storage DDL for the selected DBMS pack.

## Context

The demo compiles `.poly` source through `Poly.DslCompiler` and renders every
catalog artifact in `Poly.Demo/Poly.Demo.Shared/Services/PolyIdeCompiler.cs`.
`Poly.Demo/Poly.Demo.Shared/Pages/Ide.razor` lays out the artifact list and the
bottom panel that previews one artifact at a time. The DBMS pack is already a
dropdown on the page, so the DDL the compiler produces already reflects the
chosen pack.

## Steps

1. Add a `Storage` entry to `GroupOrder` in `Ide.razor` so the DDL artifacts sort
   beside `Reports` instead of falling into `Other`.
2. Add a `StorageDdlPanel` component under
   `Poly.Demo/Poly.Demo.Shared/Components/` that renders the selected artifact's
   text with the same `<pre class="code">` styling the report preview uses.
3. Add the FluentUI data grid for the column list:

   ```xml
   <PackageReference Include="Microsoft.FluentUI.AspNetCore.Components" Version="5.0.0" />
   ```

   to `Poly.Demo/Poly.Demo.Shared/Poly.Demo.Shared.csproj`.
4. Add the three demo projects to `Poly.slnx` so the whole surface builds from one
   command, and wire the new panel into the existing multi-splitter on `Ide.razor`.
5. Document the tab in `Poly.Mcp/Docs/poly-dsl-guide.md`.

## Verification

- Build the whole surface: `dotnet build Poly.slnx`
- Run the tests: `dotnet test Poly.Tests/Poly.Tests.csproj`
- Load the demo page and confirm the tab renders for the Sqlite pack.

## Risks

- The MAUI head may need a rebuild after the Shared change.
- Large DDL may be slow to render; revisit if the page stalls.
