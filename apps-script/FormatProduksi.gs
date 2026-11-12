// Tempel di proyek Apps Script yang sudah memiliki konstanta SPREADSHEET_ID.
function rapikanDokumenProduksi() {
  const file = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = file.getSheetByName('Dokumen_Produksi');
  if (!sheet) throw new Error('Tab Dokumen_Produksi tidak ditemukan.');

  const headers = sheet.getRange(1, 1, 1, HEADERS.length);
  if (!HEADERS.every((name, i) => headers.getDisplayValues()[0][i] === name)) {
    throw new Error('Periksa urutan header di baris pertama.');
  }
  const rows = sheet.getMaxRows();
  const range = sheet.getRange(1, 1, rows, HEADERS.length);
  let band = range.getBandings().find(item => item.getRange().getA1Notation() === range.getA1Notation());
  if (!band && range.getBandings().length === 0) {
    band = range.applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY, true, false);
  }
  if (band) {
    band.setHeaderRowColor('#14534e').setFirstRowColor('#ffffff').setSecondRowColor('#edf6f4');
  }
  headers.setBackground('#14534e').setFontColor('#ffffff').setFontWeight('bold');
  sheet.setFrozenRows(1);
  sheet.setHiddenGridlines(true);
  sheet.setRowHeight(1, 36);
  [155, 110, 155, 200, 325, 300, 155, 195].forEach((width, i) => sheet.setColumnWidth(i + 1, width));
  if (rows > 1) sheet.getRange(2, 5, rows - 1, 2).setWrap(true);
  if (!sheet.getFilter()) range.createFilter();
  file.toast('Format Dokumen_Produksi selesai.');
}
