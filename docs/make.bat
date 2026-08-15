@ECHO OFF
pushd %~dp0
if "%SPHINXBUILD%" == "" set SPHINXBUILD=sphinx-build
%SPHINXBUILD% -M html . _build %SPHINXOPTS%
popd
