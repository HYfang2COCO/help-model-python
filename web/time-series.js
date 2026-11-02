'use strict';
// UTC date arithmetic avoids daylight-saving shifts in inclusive daily ranges.
(function(root) {
  const parseDate = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return NaN;
    const timestamp = Date.parse(value + 'T00:00:00Z');
    return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0,10) === value ? timestamp : NaN;
  };
  function rangeError(rows, start, end) {
    if (!rows.length || !Number.isFinite(parseDate(start)) || !Number.isFinite(parseDate(end))) return '请选择有效的开始和结束日期。';
    if (start > end) return '开始日期不能晚于结束日期。';
    if (start < rows[0].date || end > rows.at(-1).date) return '日期须在模拟时段内。';
    return null;
  }
  function select(rows, start, end) {
    const error = rangeError(rows, start, end);
    if (error) throw new RangeError(error);
    return rows.filter(row => row.date >= start && row.date <= end);
  }
  function recentRange(rows, days) {
    if (!rows.length || !Number.isInteger(days) || days < 1) throw new RangeError('Invalid day count');
    const end = rows.at(-1).date;
    const start = new Date(parseDate(end) - (days - 1) * 86400000).toISOString().slice(0,10);
    return {start: start < rows[0].date ? rows[0].date : start, end};
  }
  function aggregate(rows, key, step) {
    if (!['day','month','year'].includes(step)) throw new RangeError('Invalid time step');
    const size = {day:10, month:7, year:4}[step], groups = new Map();
    for (const row of rows) {
      const date = row.date.slice(0,size);
      if (!groups.has(date)) groups.set(date, {date, value:0, days:0, start:row.date, end:row.date});
      const group = groups.get(date);
      group.value += row[key]; group.days++; group.end = row.date;
    }
    return [...groups.values()];
  }
  const api = Object.freeze({rangeError, select, recentRange, aggregate});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.HELP_TIME_SERIES = api;
})(globalThis);
