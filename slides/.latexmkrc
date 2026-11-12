# latexmk settings for all decks in slides/ (used by `make slides`).
$pdf_mode = 1;            # pdflatex
$out_dir = 'build';       # git-ignored
$aux_dir = 'build';
ensure_path('TEXINPUTS', './common//', './figures//');
