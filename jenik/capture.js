/* 아마존 Best Sellers 순위 캡처 스니펫.
 *
 * 사용법
 *   1. https://www.amazon.com/gp/bestsellers/beauty/11061121 을 연다
 *      (페이셜 마스크 — 마스크 전용 카테고리. 상위 노드 11062031은 세럼·
 *       여드름 패치가 섞여 들어와 2026-07-19에 갈아탔다)
 *   2. 브라우저 콘솔에 이 파일 내용을 붙여넣고 실행
 *   3. 출력된 JSON을 파일로 저장한 뒤
 *      python amazon.py --ingest <파일>
 *
 * 자동화하지 않는 이유는 README '왜 수동인가' 참조.
 * 페이지 구조가 바뀌면 여기만 고치면 된다. items가 20개 미만이면
 * 셀렉터가 깨진 것이니 ingest 전에 반드시 확인할 것.
 */
(() => {
  const items = Array.from(document.querySelectorAll('div[id^="gridItemRoot"]'))
    .map(el => {
      const rank = parseInt((el.querySelector('.zg-bdg-text')?.textContent || '')
        .replace('#', '')) || null;
      const asin = (el.querySelector('a[href*="/dp/"]')?.href
        .match(/\/dp\/([A-Z0-9]{10})/) || [])[1] || null;
      const title = (el.querySelector('a[href*="/dp/"] div[class*="line-clamp"]')
        ?.textContent || '').trim();
      // '별 5개 중 4.6' — 마지막 숫자가 평점이다. 첫 숫자를 쓰면 전부 5.0이 된다
      const nums = (el.querySelector('.a-icon-alt')?.textContent || '').match(/[\d.]+/g) || [];
      const rating = nums.length ? parseFloat(nums[nums.length - 1]) : null;
      const revEl = el.querySelector('.a-size-small.a-color-tertiary, span.a-size-small');
      const reviews = parseInt(((revEl?.textContent || '').match(/[\d,]+/) || [''])[0]
        .replace(/,/g, '')) || null;
      return { rank, asin, title, rating, reviews };
    })
    .filter(x => x.rank && x.asin);

  const seen = new Set();
  const uniq = items.filter(x => !seen.has(x.rank) && seen.add(x.rank))
    .sort((a, b) => a.rank - b.rank);

  return JSON.stringify({
    date: new Date().toISOString().slice(0, 10),
    node: location.pathname.match(/(\d+)$/)?.[1] || '',
    category: document.title,
    items: uniq.slice(0, 20),
  }, null, 1);
})()
