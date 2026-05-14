@echo off
REM Headless Ghidra batch RE for all 15 Capcom DC games.
REM For each game:
REM   1. Import the game's 1ST_READ.BIN as an SH-4 little-endian raw binary at 0x8C010000
REM   2. Apply every Katana / Naomi / Kunoichi FIDB
REM   3. Run AutoAnalysis to recover library function names
REM   4. Dump named functions + strings to JSON for downstream consumption
REM
REM Output: D:\DC_CapcomTranslationTools\spawn_re_ghidra\ghidra_dumps\<program_name>.json
REM
REM Per-binary runtime: 3–10 minutes. Total wall time: 1–3 hours.

setlocal
set GHIDRA=D:\Ghidra\ghidra_12.0.4_PUBLIC_20260303\ghidra_12.0.4_PUBLIC
set HEADLESS=%GHIDRA%\support\analyzeHeadless.bat
set PROJ_DIR=D:\DC_CapcomTranslationTools\spawn_re_ghidra\ghidra_project
set SCRIPT_DIR=D:\DC_CapcomTranslationTools\spawn_re_ghidra
set OUT_DIR=D:\DC_CapcomTranslationTools\spawn_re_ghidra\ghidra_dumps
set RC2=D:\Capcom Dreamcast  Games - Joe Patched\RC2 Translated

mkdir "%PROJ_DIR%" 2>nul
mkdir "%OUT_DIR%" 2>nul

REM Process each game. Use the patches/1ST_READ.BIN where available, fallback to extracted/.
call :run_one "spawn"                "%RC2%\Spawn - In the Demon's Hand (JP)\patches\1ST_READ.BIN"
call :run_one "cvs_pro"              "%RC2%\Capcom vs. SNK - Millennium Fight 2000 Pro (JP)\extracted\1ST_READ.BIN"
call :run_one "heavy_metal"          "%RC2%\Heavy Metal - Geomatrix (JP)\extracted\1ST_READ.BIN"
call :run_one "jojo"                 "%RC2%\JoJo_s Bizarre Adventure[ (JP)\extracted\1ST_READ.BIN"
call :run_one "mvc2"                 "%RC2%\Marvel vs. Capcom 2 - New Age of Heroes (JP)\extracted\1ST_READ.BIN"
call :run_one "net_de_tennis"        "%RC2%\Net de Tennis (JP)\extracted\1ST_READ.BIN"
call :run_one "power_stone_2"        "%RC2%\Power Stone 2 (JP)\extracted\1ST_READ.BIN"
call :run_one "project_justice"      "%RC2%\Project Justice (JP)\extracted\1ST_READ.BIN"
call :run_one "sf3_3rd_strike"       "%RC2%\Street Fighter III 3rd Strike - Fight for the Future (JP)\extracted\1ST_READ.BIN"
call :run_one "sfz3_ms"              "%RC2%\Street Fighter Zero 3  for Matching Service (JP)\extracted\1ST_READ.BIN"
call :run_one "spfii_ms"             "%RC2%\Super Puzzle Fighter IIX for Matching Service (JP)\extracted\1ST_READ.BIN"
call :run_one "ssfiix_ms"            "%RC2%\Super Street Fighter IIX for Matching Service - Grand Master Challenge (JP)\extracted\1ST_READ.BIN"
call :run_one "taisen_net_gimmick"   "%RC2%\Taisen Net Gimmick - Capcom & Psikyo All Stars (JP)\extracted\1ST_READ.BIN"
call :run_one "tech_romancer_ms"     "%RC2%\Tech Romancer for Matching Service (JP)\extracted\1ST_READ.BIN"
call :run_one "vampire_chronicle_ms" "%RC2%\Vampire Chronicle for Matching Service (JP)\extracted\1ST_READ.BIN"

echo === ALL DONE ===
goto :eof

:run_one
echo === %~1 ===
if not exist "%~2" (
  echo MISSING: %~2
  goto :eof
)
call "%HEADLESS%" "%PROJ_DIR%" "%~1" -import "%~2" ^
  -processor "SuperH:LE:32:SH-4" ^
  -loader BinaryLoader ^
  -loader-image-base 0x8C010000 ^
  -overwrite ^
  -scriptPath "%SCRIPT_DIR%" ^
  -postScript AttachAllFidbs.java ^
  -postScript DumpSymbolsAndStrings.java -Ddump.outDir="%OUT_DIR%"
goto :eof
