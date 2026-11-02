// Run with Node: node --test tests/test_time_series.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const {select, recentRange, aggregate, rangeError} = require('../web/time-series.js');
const rows = Array.from({length:731}, (_,i) => ({
  date:new Date(Date.UTC(2024,0,1)+i*86400000).toISOString().slice(0,10),
  rain:i%7, leakage:i/100000
}));

test('inclusive leap-day and single-day selection, with no source mutation', () => {
  const snapshot=JSON.stringify(rows);
  assert.deepEqual(select(rows,'2024-02-28','2024-03-01').map(r=>r.date),['2024-02-28','2024-02-29','2024-03-01']);
  const day=select(rows,'2024-02-29','2024-02-29');
  assert.equal(day.length,1);
  assert.equal(aggregate(day,'rain','year')[0].value,day[0].rain);
  assert.equal(JSON.stringify(rows),snapshot);
});
test('recent ranges are inclusive, anchored at simulation end, and capped', () => {
  for (const days of [30,90,365]) {
    const range=recentRange(rows,days);
    assert.equal(range.end,'2025-12-31');
    assert.equal(select(rows,range.start,range.end).length,days);
  }
  const short=rows.slice(60,63);
  assert.deepEqual(recentRange(short,30),{start:'2024-03-01',end:'2024-03-03'});
});
test('monthly sums include only selected days in partial months', () => {
  const source=select(rows,'2024-01-30','2024-03-02');
  const monthly=aggregate(source,'rain','month');
  assert.deepEqual(monthly.map(r=>[r.date,r.days]),[['2024-01',2],['2024-02',29],['2024-03',2]]);
  for (const month of monthly) assert.equal(month.value,source.filter(r=>r.date.startsWith(month.date)).reduce((s,r)=>s+r.rain,0));
});
test('year sums across a partial year preserve each flux total', () => {
  const source=select(rows,'2024-12-30','2025-01-02');
  for (const flux of ['rain','leakage']) {
    const annual=aggregate(source,flux,'year');
    assert.deepEqual(annual.map(r=>[r.date,r.days]),[['2024',2],['2025',2]]);
    assert.ok(Math.abs(annual.reduce((s,r)=>s+r.value,0)-source.reduce((s,r)=>s+r[flux],0))<1e-12);
  }
});
test('empty, invalid, reversed and out-of-bounds ranges reject rather than silently clip', () => {
  for (const [start,end] of [['','2024-01-01'],['2024-02-30','2024-03-01'],['2024-03-02','2024-03-01'],['2023-12-31','2024-01-01'],['2025-12-31','2026-01-01']]) {
    assert.ok(rangeError(rows,start,end));
    assert.throws(()=>select(rows,start,end),RangeError);
  }
  assert.throws(()=>select([],'2024-01-01','2024-01-01'),RangeError);
});
test('all daily values and tiny nonzero fluxes remain unchanged', () => {
  const daily=aggregate(rows,'leakage','day');
  assert.deepEqual(daily.map(r=>r.value),rows.map(r=>r.leakage));
  assert.equal(daily[1].value,0.00001);
  assert.equal(aggregate([{date:'2024-01-01',rain:0}],'rain','month')[0].value,0);
  assert.throws(()=>aggregate(rows,'rain','hour'),RangeError);
});
