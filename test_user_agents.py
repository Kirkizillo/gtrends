"""
Test to verify User-Agent rotation is working.
"""
import logging
import sys

import config
from trends_scraper import TrendsScraper, USER_AGENTS

logging.basicConfig(
    level=logging.INFO,
    format=config.LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def test_user_agent_rotation():
    """Test that User-Agents rotate properly."""
    logger.info("="*60)
    logger.info("USER-AGENT ROTATION TEST")
    logger.info("="*60)

    logger.info(f"\nTotal User-Agents available: {len(USER_AGENTS)}\n")

    logger.info("Testing 5 consecutive initializations:")
    logger.info("-" * 60)

    user_agents_used = []

    for i in range(5):
        logger.info(f"\nInitialization #{i+1}:")
        scraper = TrendsScraper()

        # Extract the User-Agent from the pytrends session
        if hasattr(scraper.pytrends, 'requests_args'):
            ua = scraper.pytrends.requests_args.get('headers', {}).get('User-Agent', 'N/A')
            user_agents_used.append(ua)
            logger.info(f"  User-Agent: {ua[:80]}...")
        else:
            logger.warning("  Could not extract User-Agent")

    logger.info("\n" + "="*60)
    logger.info("ROTATION ANALYSIS")
    logger.info("="*60)

    unique_uas = set(user_agents_used)
    logger.info(f"\nUnique User-Agents used: {len(unique_uas)} out of {len(user_agents_used)} initializations")

    if len(unique_uas) > 1:
        logger.info("SUCCESS: User-Agents are rotating properly")
    elif len(unique_uas) == 1:
        logger.warning("WARNING: Same User-Agent used every time (might be random chance)")
    else:
        logger.error("ERROR: No User-Agents detected")

    logger.info("\n" + "="*60)
    logger.info("AVAILABLE USER-AGENTS BY BROWSER")
    logger.info("="*60)

    browsers = {
        'Chrome Windows': 0,
        'Firefox Windows': 0,
        'Chrome macOS': 0,
        'Safari macOS': 0,
        'Firefox macOS': 0,
        'Chrome Linux': 0,
        'Firefox Linux': 0,
        'Edge Windows': 0,
        'Edge macOS': 0,
    }

    for ua in USER_AGENTS:
        if 'Chrome' in ua and 'Windows' in ua and 'Edg' not in ua:
            browsers['Chrome Windows'] += 1
        elif 'Firefox' in ua and 'Windows' in ua:
            browsers['Firefox Windows'] += 1
        elif 'Chrome' in ua and 'Macintosh' in ua and 'Edg' not in ua:
            browsers['Chrome macOS'] += 1
        elif 'Safari' in ua and 'Version' in ua:
            browsers['Safari macOS'] += 1
        elif 'Firefox' in ua and 'Macintosh' in ua:
            browsers['Firefox macOS'] += 1
        elif 'Chrome' in ua and 'Linux' in ua:
            browsers['Chrome Linux'] += 1
        elif 'Firefox' in ua and 'Linux' in ua:
            browsers['Firefox Linux'] += 1
        elif 'Edg' in ua and 'Windows' in ua:
            browsers['Edge Windows'] += 1
        elif 'Edg' in ua and 'Macintosh' in ua:
            browsers['Edge macOS'] += 1

    for browser, count in browsers.items():
        if count > 0:
            logger.info(f"  {browser}: {count} User-Agents")

    logger.info("\n" + "="*60)


if __name__ == "__main__":
    test_user_agent_rotation()
