import assert from 'node:assert/strict';
import {parseQuoteText, repairTableQuote} from './quote-parser.js';

const sw = parseQuoteText(`
1) Gateway 데이터 연동 6,006
소프트웨어 ProdEX AI Smart 1 1,500,000 9,000,000
`);
assert.equal(sw.items.length, 1);
assert.equal(sw.items[0].category, 'S/W');
assert.equal(sw.items[0].qty, 6);
assert.equal(sw.items[0].unit_price, 1_500_000);
assert.equal(sw.items[0].amount, 9_000_000);

const hw = repairTableQuote(
  parseQuoteText('하드웨어 CNC 레이저 용접 시스템 1 42,000,000 42,000,000'),
  '품목 모델명 수량 단가 합계 하드웨어 CNC 레이저 용접 시스템',
  {qtyText:'1', unitText:'42,000,000', amountText:'42,000,000'}
);
assert.equal(hw.items.length, 1);
assert.equal(hw.items[0].category, 'H/W');
assert.equal(hw.items[0].qty, 1);
assert.equal(hw.items[0].unit_price, 42_000_000);
assert.equal(hw.items[0].amount, 42_000_000);

const repairedSw = repairTableQuote(
  parseQuoteText('1) Gateway 데이터 연동 6,006\n소프트웨어 ProdEX AI Smart 1,500,000 9,000,000'),
  '품목 모델명 수량 단가 합계 소프트웨어 ProdEX AI Smart',
  {qtyText:'6', unitText:'1,500,000', amountText:'9,000,000'}
);
assert.equal(repairedSw.items.length, 1);
assert.equal(repairedSw.items[0].qty, 6);
assert.equal(repairedSw.total, 9_000_000);

console.log('quote-parser tests passed');
