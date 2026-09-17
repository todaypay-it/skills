import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

function parseArgs(argv) {
  const result = {};
  for (let index = 2; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || value === undefined) throw new Error(`Invalid argument near ${key || '<end>'}`);
    result[key.slice(2)] = value;
  }
  if (!result.input || !result['output-dir']) throw new Error('Usage: build_workbooks.js --input reconciliation.json --output-dir DIR');
  return result;
}

const args = parseArgs(process.argv);
const inputPath = path.resolve(args.input);
const outputDir = path.resolve(args['output-dir']);
const data = JSON.parse(await fs.readFile(inputPath, 'utf8'));
await fs.mkdir(outputDir, { recursive: true });

const colors = {
  navy: '#24466B', stripe: '#D7EFFA', light: '#EAF2F8', text: '#172B42',
  muted: '#64748B', red: '#B91C1C', redFill: '#FEE2E2', white: '#FFFFFF',
};
const meta = data.meta;
const summaryData = data.summary;
const currency = meta.currency;
const start = meta.period_start;
const end = meta.period_end;
const startCompact = start.replaceAll('-', '');
const endCompact = end.replaceAll('-', '');
const flowDomain = meta.flow_funding_domain;
const accountType = meta.flow_account_type;
const period = `${start} 至 ${end}，按创建日期，${meta.business_time_zone}`;
const flowPeriod = `${meta.flow_period_start} 至 ${meta.flow_period_end}（目标截止 ${meta.flow_target_end}）`;
const flowCompleteness = meta.flow_window_complete
  ? '全部订单均已获得创建日期后 3 天的完整流水观察窗口。'
  : `流水仅查询至 ${meta.flow_period_end}；靠近订单期末的未覆盖订单仍处于观察期。`;
const cutoff = `查询截止：${meta.as_of_business}（业务时区）；${meta.as_of_user}（用户时区）`;
const completeness = meta.period_complete
  ? '期间内每个业务日期均已结束。'
  : `${end} 为截至查询时刻的当日快照，其余已结束日期为完整业务日。`;
let tableSequence = 0;

function columnName(index) {
  let result = '';
  for (let value = index + 1; value; value = Math.floor((value - 1) / 26)) {
    result = String.fromCharCode(65 + ((value - 1) % 26)) + result;
  }
  return result;
}

function money(value) {
  const number = Number(value || 0);
  return `${number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })} ${currency}`;
}

function asText(key, value) {
  if (value === null || value === undefined) return '';
  let result = String(value);
  if (result.startsWith('=')) result = `'${result}`;
  if (/^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$/.test(result)) result = `'${result}`;
  if (/(?:流水ID|账户ID|商户编号)/.test(key) && /^\d{16,}$/.test(result)) result = `'${result}`;
  return result;
}

function rowsAsText(rows, keys) {
  return rows.map((row) => keys.map((key) => asText(key, row[key])));
}

function prepareSheet(workbook, name, lastColumn, lastRow) {
  const sheet = workbook.worksheets.getItem(name);
  sheet.showGridLines = false;
  sheet.tabColor = colors.navy;
  const full = sheet.getRange(`A1:${lastColumn}${lastRow}`);
  full.setNumberFormat('@');
  full.format.font = { name: 'Arial', size: 10, color: colors.text };
  full.format.verticalAlignment = 'center';
  full.format.rowHeight = 22;
  sheet.getRange(`A1:${lastColumn}1`).format.rowHeight = 12;
  sheet.getRange(`A2:${lastColumn}2`).format.rowHeight = 30;
  sheet.getRange('A2').format.font = { name: 'Arial', size: 15, bold: true, color: colors.text };
  sheet.getRange(`A3:${lastColumn}3`).format.borders = { bottom: { style: 'thin', color: '#8298B0' } };
  return sheet;
}

function chooseWidth(key) {
  if (/导出任务ID/.test(key)) return 44;
  if (/平台订单号|商户订单号|订单号|银行单号/.test(key)) return 46;
  if (/流水ID/.test(key)) return 48;
  if (/账户ID|商户编号/.test(key)) return 30;
  if (/关联号/.test(key)) return 56;
  if (/用户信息/.test(key)) return 70;
  if (/时间|UTC/.test(key)) return 31;
  if (/日期/.test(key)) return 18;
  if (/金额|余额|费率|手续费/.test(key)) return 21;
  if (/状态|类型|方式|方向/.test(key)) return 19;
  return 24;
}

function detailSheet(workbook, name, title, rows, keys, options = {}) {
  if (!keys.length) keys = ['说明'];
  const lastColumn = columnName(keys.length - 1);
  const finalRow = Math.max(10, 9 + rows.length);
  const sheet = prepareSheet(workbook, name, lastColumn, finalRow);
  const introLast = columnName(Math.min(keys.length, 6) - 1);
  sheet.mergeCells(`A2:${introLast}2`);
  sheet.getRange('A2').values = [[title]];
  sheet.mergeCells(`A4:${introLast}4`);
  sheet.getRange('A4').values = [[options.scope || period]];
  sheet.getRange('A5:B5').values = [[options.countLabel || '记录条数', String(rows.length)]];
  sheet.mergeCells(`A6:${introLast}6`);
  sheet.getRange('A6').values = [[options.source || '来源：TDayPay 商户导出']];
  sheet.getRange('A6').format.font = { name: 'Arial', size: 10, color: colors.muted, italic: true };
  sheet.mergeCells(`A7:${introLast}7`);
  sheet.getRange('A7').values = [[options.note || '所有字段均以文本格式保存。']];
  sheet.mergeCells(`A8:${introLast}8`);
  sheet.getRange('A8').values = [[`${cutoff}；${completeness}`]];
  sheet.getRange('A8').format.font = { name: 'Arial', size: 10, color: colors.muted };
  sheet.getRange(`A9:${lastColumn}9`).values = [keys];
  sheet.getRange(`A9:${lastColumn}9`).format = {
    fill: colors.navy,
    font: { name: 'Arial', size: 10, bold: true, color: colors.white },
    horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 30,
  };
  if (rows.length) {
    sheet.getRange(`A10:${lastColumn}${finalRow}`).values = rowsAsText(rows, keys);
    for (let row = 10; row <= finalRow; row += 1) {
      if ((row - 10) % 2 === 0) sheet.getRange(`A${row}:${lastColumn}${row}`).format.fill = colors.stripe;
    }
    sheet.tables.add(`A9:${lastColumn}${finalRow}`, true, `TextTable${++tableSequence}`);
  } else {
    sheet.mergeCells(`A10:${introLast}10`);
    sheet.getRange('A10').values = [[options.empty || '无符合条件的记录']];
    sheet.getRange('A10').format.font = { name: 'Arial', size: 10, color: colors.muted, italic: true };
  }
  keys.forEach((key, index) => {
    const letter = columnName(index);
    sheet.getRange(`${letter}1:${letter}${finalRow}`).format.columnWidth = chooseWidth(key);
    sheet.getRange(`${letter}10:${letter}${finalRow}`).format.horizontalAlignment = 'left';
  });
  sheet.freezePanes.freezeRows(9);
  return sheet;
}

function summarySheet(workbook, name, title, rows) {
  const finalRow = 5 + rows.length;
  const sheet = prepareSheet(workbook, name, 'C', finalRow);
  sheet.mergeCells('A2:C2');
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A5:C5').values = [['项目', '结果', '口径 / 说明']];
  sheet.getRange('A5:C5').format = {
    fill: colors.navy,
    font: { name: 'Arial', size: 10, bold: true, color: colors.white },
    horizontalAlignment: 'center', rowHeight: 28,
  };
  sheet.getRange(`A6:C${finalRow}`).values = rows.map((row) => row.map((value) => asText('结果', value)));
  for (let row = 6; row <= finalRow; row += 1) {
    if (row % 2 === 0) sheet.getRange(`A${row}:C${row}`).format.fill = colors.light;
  }
  sheet.getRange(`A1:A${finalRow}`).format.columnWidth = 42;
  sheet.getRange(`B1:B${finalRow}`).format.columnWidth = 31;
  sheet.getRange(`C1:C${finalRow}`).format.columnWidth = 82;
  sheet.getRange(`B6:B${finalRow}`).format.horizontalAlignment = 'left';
  sheet.freezePanes.freezeRows(5);
  return sheet;
}

async function finish(workbook, filename) {
  workbook.recalculate();
  const errorScan = await workbook.inspect({
    kind: 'match',
    searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
    options: { useRegex: true, maxResults: 100 },
    summary: 'final formula error scan',
    maxChars: 3000,
  });
  if ((errorScan.ndjson || '').includes('"kind":"match"')) {
    throw new Error(`Spreadsheet error token found in ${filename}: ${errorScan.ndjson}`);
  }
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange(true);
    const values = used?.values || [];
    const rowCount = Math.max(values.length, 1);
    const columnCount = Math.max(values[0]?.length || 1, 1);
    const lastColumn = columnName(Math.min(columnCount, 8) - 1);
    await workbook.inspect({
      kind: 'table', range: `'${sheet.name}'!A1:${lastColumn}${Math.min(rowCount, 20)}`,
      include: 'values,formulas', tableMaxRows: 20, tableMaxCols: 8, maxChars: 5000,
    });
    await workbook.render({
      sheetName: sheet.name,
      range: `A1:${lastColumn}${Math.min(Math.max(rowCount, 14), 32)}`,
      scale: 1.25,
      format: 'png',
    });
  }
  const file = await SpreadsheetFile.exportXlsx(workbook);
  const target = path.join(outputDir, filename);
  await file.save(target);
  return target;
}

const merchant = data.success[0]?.['商户编号'] || '';
const commonSummary = [
  ['范围', `${currency}，代收及代付`, period],
  ['当前商户', asText('商户编号', merchant), '取自 TDayPay 成功订单导出'],
  ['查询截止', meta.as_of_business, `业务时区；用户时区 ${meta.as_of_user}`],
  ['期间完整性', meta.period_complete ? '完整期间' : '当日快照', completeness],
  ['数据格式', '全部文本', '标识、日期、金额及导出字段均以文本保存'],
  ['匹配键', '完整平台订单号', '精确字符串匹配，不截断、不转数字'],
  ['流水查询期间', flowPeriod, flowCompleteness],
];
const outputFiles = [];

{
  const workbook = Workbook.create();
  workbook.worksheets.add('对账概览');
  workbook.worksheets.add('对账明细');
  summarySheet(workbook, '对账概览', `${currency} 成功订单对账总结`, [
    ...commonSummary,
    ['我方成功订单', String(summaryData.ours_count), '仅 SUCCESS 订单'],
    ['TDayPay 成功订单', String(summaryData.tdaypay_success_count), `${summaryData.payment_count} 笔代收，${summaryData.payout_count} 笔代付`],
    ['双方匹配订单', String(summaryData.matched_count), '按完整平台订单号精确匹配'],
    ['我方有、TDayPay 无', String(summaryData.ours_only_count), '详见差异订单工作簿'],
    ['TDayPay 有、我方无', String(summaryData.tdaypay_only_count), '详见差异订单工作簿'],
    ['字段差异订单', String(summaryData.field_discrepancy_count), '核对商户订单号、金额、币种及可用的支付类型'],
    ['我方成功总金额', money(summaryData.ours_amount), '文本金额'],
    ['TDayPay 成功总金额', money(summaryData.tdaypay_success_amount), '文本金额'],
    ['金额差（我方减 TDayPay）', money(summaryData.amount_delta), '文本金额'],
    ['TDayPay 未结算笔数', String(summaryData.unsettled_count), '结算状态 UNCHECK'],
    ['TDayPay 未结算金额', money(summaryData.unsettled_amount), '详见未结算订单工作簿'],
    ['结算状态缺失或未知笔数', String(summaryData.settlement_unknown_count || 0), '不计作已结算或明确未结算；详见未结算订单工作簿'],
    ['结算状态缺失或未知金额', money(summaryData.settlement_unknown_amount || 0), '需要 TDayPay 补充状态后确认'],
    ['有指定流水的成功订单', String(summaryData.covered_order_count), '按完整平台订单号匹配'],
    ['未查到指定流水的成功订单', String(summaryData.missing_flow_count), '详见未查到流水订单工作簿'],
    ['流水观察期未结束订单', String(summaryData.pending_flow_observation_count || 0), '不计作缺少流水'],
    ['流水核查口径', `${flowDomain} + ${accountType}`, 'TDayPay 导出实际枚举'],
    ['指定口径流水条数', String(summaryData.flow_raw_count), `其中 ${summaryData.matched_flow_count} 条关联本期成功订单`],
    ['订单号匹配但超窗流水', String(summaryData.out_of_window_flow_count || 0), '未计作订单流水覆盖'],
    ['系统来源文件', path.basename(meta.source_file), meta.source_file],
  ]);
  detailSheet(workbook, '对账明细', '双方成功订单核对依据', data.matches, ['平台订单号', '商户订单号', '我方金额', 'TDayPay金额', '金额差', '币种', '支付类型', '字段核查结果'], {
    countLabel: '匹配订单笔数', source: '来源：系统订单文件与 TDayPay 成功订单导出',
    note: '按完整平台订单号精确匹配；所有字段均以文本格式保存。',
  });
  outputFiles.push(await finish(workbook, `${currency}_对账总结_${startCompact}-${endCompact}.xlsx`));
}

{
  const workbook = Workbook.create();
  workbook.worksheets.add('我方有TDayPay无');
  workbook.worksheets.add('TDayPay有我方无');
  detailSheet(workbook, '我方有TDayPay无', '我方成功、TDayPay 成功订单未查到', data.only_ours, data.system_headers, {
    countLabel: '差异订单笔数', source: '来源：系统订单文件与 TDayPay 成功订单导出',
    note: `差异 ${summaryData.ours_only_count} 笔，金额 ${money(summaryData.ours_only_amount)}。`, empty: '无差异订单',
  });
  detailSheet(workbook, 'TDayPay有我方无', 'TDayPay 成功、我方列表未列出', data.only_theirs, data.order_headers, {
    countLabel: '差异订单笔数', source: '来源：系统订单文件与 TDayPay 成功订单导出',
    note: `差异 ${summaryData.tdaypay_only_count} 笔，金额 ${money(summaryData.tdaypay_only_amount)}。`, empty: '无差异订单',
  });
  outputFiles.push(await finish(workbook, `${currency}_差异订单_${startCompact}-${endCompact}.xlsx`));
}

{
  const workbook = Workbook.create();
  workbook.worksheets.add('明确未结算');
  workbook.worksheets.add('结算状态待核实');
  detailSheet(workbook, '明确未结算', `${currency} 成功但明确未结算订单`, data.unsettled, data.order_headers, {
    countLabel: '未结算订单笔数', note: `筛选 SUCCESS 且结算状态 UNCHECK；共 ${summaryData.unsettled_count} 笔，金额 ${money(summaryData.unsettled_amount)}。`,
  });
  detailSheet(workbook, '结算状态待核实', `${currency} 成功订单结算状态缺失或未知`, data.settlement_unknown || [], data.order_headers, {
    countLabel: '待核实订单笔数',
    note: `结算状态不是 CHECKED 或 UNCHECK；共 ${summaryData.settlement_unknown_count || 0} 笔，金额 ${money(summaryData.settlement_unknown_amount || 0)}。这些订单不计作明确未结算。`,
    empty: '无结算状态缺失或未知的成功订单',
  });
  outputFiles.push(await finish(workbook, `${currency}_未结算订单_${startCompact}-${endCompact}.xlsx`));
}

{
  const workbook = Workbook.create();
  workbook.worksheets.add('导出概览');
  workbook.worksheets.add('成功订单');
  workbook.worksheets.add('逐日导出结果');
  const dateRows = Object.entries(summaryData.dates).map(([dateKey, count]) => [dateKey, String(count), dateKey === endCompact && !meta.period_complete ? '截至查询时刻的当日快照' : '完整业务日期']);
  summarySheet(workbook, '导出概览', `TDayPay ${currency} 成功订单导出`, [
    ...commonSummary,
    ['成功订单笔数', String(summaryData.tdaypay_success_count), '订单状态 SUCCESS'],
    ['成功订单金额', money(summaryData.tdaypay_success_amount), '文本金额'],
    ['代收成功笔数', String(summaryData.payment_count), 'PAYMENT'],
    ['代付成功笔数', String(summaryData.payout_count), 'PAYOUT'],
    ['已结算笔数', String(summaryData.settled_count), '结算状态 CHECKED'],
    ['未结算笔数', String(summaryData.unsettled_count), '结算状态 UNCHECK'],
    ['结算状态缺失或未知笔数', String(summaryData.settlement_unknown_count || 0), '不计作明确未结算'],
    ...dateRows,
    ['订单导出任务数', String(meta.order_exports.length), '逐日导出，每个任务仅覆盖一个业务日期'],
  ]);
  detailSheet(workbook, '成功订单', `TDayPay ${currency} 成功订单`, data.success, data.order_headers, {
    countLabel: '成功订单笔数', note: `${summaryData.payment_count} 笔代收成功，${summaryData.payout_count} 笔代付成功。`,
  });
  const orderExportRows = meta.order_exports.length ? meta.order_exports : meta.order_export_files.map((file) => ({ '本地文件': file }));
  detailSheet(workbook, '逐日导出结果', 'TDayPay 订单逐日导出结果', orderExportRows, Object.keys(orderExportRows[0] || { '说明': '' }), {
    countLabel: '导出记录数', source: '来源：mc_get_order_export_status', note: '每个订单导出任务仅覆盖一个业务日期。',
  });
  outputFiles.push(await finish(workbook, `TDayPay_${currency}_成功订单_${startCompact}-${endCompact}.xlsx`));
}

{
  const workbook = Workbook.create();
  workbook.worksheets.add('未查到流水订单');
  workbook.worksheets.add('观察期未结束');
  detailSheet(workbook, '未查到流水订单', `${currency} 成功订单未查到指定记账流水`, data.missing, [...data.order_headers, '流水核查结果'], {
    countLabel: '缺少流水订单笔数', source: `来源：TDayPay 成功订单及 ${flowDomain} + ${accountType} 流水导出`,
    note: summaryData.missing_flow_count
      ? `${summaryData.missing_flow_count} 笔成功订单在创建日起至后 3 天内未查到 ${flowDomain} + ${accountType} 流水。`
      : `完整观察期内没有确认缺少流水的成功订单。`,
    empty: '无缺少流水的成功订单',
    scope: `订单期间：${period}；流水期间：${flowPeriod}`,
  });
  detailSheet(workbook, '观察期未结束', `${currency} 成功订单流水观察期未结束`, data.pending_flow_observation || [], [...data.order_headers, '流水核查结果'], {
    countLabel: '观察中订单笔数', source: `来源：TDayPay 成功订单及 ${flowDomain} + ${accountType} 流水导出`,
    note: `${summaryData.pending_flow_observation_count || 0} 笔订单尚未获得创建日期后 3 天的完整流水观察窗口，不计作缺少流水。`,
    empty: '无观察期未结束的订单',
    scope: `订单期间：${period}；流水期间：${flowPeriod}`,
  });
  outputFiles.push(await finish(workbook, `${currency}_${flowDomain}_${accountType}_未查到流水订单_${startCompact}-${endCompact}.xlsx`));
}

{
  const workbook = Workbook.create();
  workbook.worksheets.add('成功订单关联流水');
  workbook.worksheets.add('订单号匹配但超窗');
  workbook.worksheets.add('全部查询流水');
  workbook.worksheets.add('查询结果');
  const enrichmentHeaders = ['关联成功订单创建日期', '关联商户订单号', '流水距订单创建天数', '订单流水窗口结果'];
  const rawFlowHeaders = data.flow_headers.filter((header) => !enrichmentHeaders.includes(header));
  detailSheet(workbook, '成功订单关联流水', `${currency} 成功订单指定口径关联流水`, data.matched_flows, data.flow_headers, {
    countLabel: '关联流水条数', source: `来源：mc_export_merchant_account_flows；${flowDomain} + ${accountType}`,
    note: `按完整平台订单号关联，并限制在订单创建日起至后 3 天；${summaryData.matched_flow_count} 条流水覆盖本期成功订单。`,
    scope: `订单期间：${period}；流水期间：${flowPeriod}`,
  });
  detailSheet(workbook, '订单号匹配但超窗', `${currency} 订单号匹配但超出 3 天窗口的流水`, data.out_of_window_flows || [], data.flow_headers, {
    countLabel: '超窗流水条数', source: `来源：mc_export_merchant_account_flows；${flowDomain} + ${accountType}`,
    note: `${summaryData.out_of_window_flow_count || 0} 条流水的平台订单号匹配，但创建日期不在订单创建日起至后 3 天内，未计作覆盖。`,
    empty: '无订单号匹配但超窗的流水',
    scope: `订单期间：${period}；流水期间：${flowPeriod}`,
  });
  detailSheet(workbook, '全部查询流水', `TDayPay ${currency} ${flowDomain} + ${accountType} 流水`, data.raw_flows, rawFlowHeaders, {
    countLabel: '指定口径流水条数', source: '来源：mc_export_merchant_account_flows',
    note: `精确筛选资金域 ${flowDomain} 及账户类型 ${accountType}。`,
    scope: `流水查询期间：${flowPeriod}`,
  });
  const flowExportRows = meta.flow_exports.length ? meta.flow_exports : meta.flow_export_files.map((file) => ({ '本地文件': file }));
  detailSheet(workbook, '查询结果', '记账流水导出任务', flowExportRows, Object.keys(flowExportRows[0] || { '说明': '' }), {
    countLabel: '导出记录数', source: '来源：mc_get_account_flow_export_status',
    note: `日期范围超过七天时分片导出，再按流水ID去重。${flowCompleteness}`,
    scope: `流水查询期间：${flowPeriod}`,
  });
  outputFiles.push(await finish(workbook, `TDayPay_${currency}_${flowDomain}_${accountType}_记账流水_${startCompact}-${endCompact}.xlsx`));
}

console.log(JSON.stringify({ outputDir, files: outputFiles }, null, 2));
