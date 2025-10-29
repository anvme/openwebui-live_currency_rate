"""
title: Live Currency Rate
author: anvme
author_url: https://anvcore.com
github: https://github.com/anvme/
github_repo: https://github.com/anvme/openwebui-live_currency_rate
version: 0.1.0
requirements: requests, packaging
description: 
    Tool to get live currency rates and convert between fiat and cryptocurrencies.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import requests
import json
import time
from datetime import datetime, timedelta
from packaging import version


class Tools:
    class Valves(BaseModel):
        ENABLE_UPDATE_CHECK: bool = Field(
            default=True,
            description="Enable automatic update check and notification for admins",
        )
        CACHE_DURATION: int = Field(
            default=180,
            description="Cache duration in seconds (default: 180 = 3 minutes)",
        )
        API_URL: str = Field(
            default="https://cdn.jsdelivr.net/gh/anvme/currency@main/latest.json",
            description="Currency API endpoint URL. Use Default, it's updating every ~30 minutes. More info at https://github.com/anvme/currency ",
        )

    # Configuration - update these for your tool
    EXT_TITLE = "Live Currency Rate"
    CURRENT_VERSION = "0.1.0"
    GITHUB_USER = "anvme"
    GITHUB_REPO = "openwebui-live_currency_rate"
    EXT_PATH = f"t/anvme/live_currency_rate"
    DATA_FILE = f"/tmp/openwebui_upd_check_{GITHUB_USER}_{GITHUB_REPO}.json"

    def __init__(self):
        self.valves = self.Valves()
        self.cache: Dict[str, Any] = {"data": None, "timestamp": 0}
        self.update_state = self._load_state()

    def _load_state(self) -> dict:
        try:
            with open(self.DATA_FILE, "r") as f:
                data = json.load(f)
                data["last_check"] = datetime.fromisoformat(data.get("last_check", "2024-01-01"))
                return data
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return {
                "last_check": datetime(2024, 1, 1),
                "latest_version": None,
                "latest_url": None,
                "has_shown_notification": False,
            }

    def _save_state(self):
        try:
            data = self.update_state.copy()
            data["last_check"] = data["last_check"].isoformat()
            with open(self.DATA_FILE, "w") as f:
                json.dump(data, f)
        except (OSError, IOError):
            pass

    def _check_github_release(self):
        try:
            url = f"https://api.github.com/repos/{self.GITHUB_USER}/{self.GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                new_version = data.get("tag_name", "").lstrip("v")
                
                version_changed = self.update_state["latest_version"] != new_version
                
                self.update_state["latest_version"] = new_version
                self.update_state["latest_url"] = data.get("html_url", "")
                
                if version_changed:
                    self.update_state["has_shown_notification"] = False
                    
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            pass
        finally:
            self.update_state["last_check"] = datetime.now()
            self._save_state()

    def _get_update_notification(self) -> str:
        if not self.update_state["latest_version"]:
            return ""
        
        try:
            if version.parse(self.update_state["latest_version"]) > version.parse(self.CURRENT_VERSION):
                github_url = f"https://github.com/{self.GITHUB_USER}/{self.GITHUB_REPO}"
                ext_url = f"https://openwebui.com/{self.EXT_PATH}"
                return (
                    f"**🔔 {EXT_TITLE} Update Available!**\nVersion {self.update_state['latest_version']} is now available.\n"
                    f"Current version: {self.CURRENT_VERSION}\n"
                    f"📦 [GitHub]({github_url}) | 🔘 [OpenWebUI]({ext_url}) | 🗒️ [Release Notes]({github_url}/releases)\n"
                )
        except (ValueError, TypeError):
            pass
        
        return ""

    def _should_check_for_updates(self, user: dict) -> bool:
        if not self.valves.ENABLE_UPDATE_CHECK:
            return False
        
        if not isinstance(user, dict) or user.get("role") != "admin":
            return False
        
        time_since_check = datetime.now() - self.update_state["last_check"]
        return time_since_check >= timedelta(hours=24)

    async def _check_and_notify_updates(self, user: dict, event_emitter):
        if self._should_check_for_updates(user):
            self._check_github_release()
        
        if not self.update_state["has_shown_notification"] and event_emitter:
            notification = self._get_update_notification()
            if notification:
                await event_emitter({"type": "message", "data": {"content": notification}})
                self.update_state["has_shown_notification"] = True
                self._save_state()

    # TOOL

    def _fetch_rates(self) -> Dict[str, Any]:
        """Fetch currency rates with caching"""
        current_time = time.time()

        # Check if cache is still valid
        if (
            self.cache["data"] is not None
            and current_time - self.cache["timestamp"] < self.valves.CACHE_DURATION
        ):
            return self.cache["data"]

        # Fetch new data
        try:
            response = requests.get(self.valves.API_URL, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Update cache
            self.cache["data"] = data
            self.cache["timestamp"] = current_time

            return data
        except Exception as e:
            # If fetch fails but we have cached data, return it
            if self.cache["data"] is not None:
                return self.cache["data"]
            raise Exception(f"Failed to fetch currency rates: {str(e)}")

    def _format_amount(self, amount: float, currency: str) -> str:
        """Format amount based on currency type"""
        crypto_currencies = ["BTC", "ETH", "SOL"]

        if currency in crypto_currencies:
            # Crypto: use more decimals
            return f"{amount:,.8f}".rstrip("0").rstrip(".")
        else:
            # Fiat: standard 2-4 decimals
            if amount >= 100:
                return f"{amount:,.2f}"
            elif amount >= 1:
                return f"{amount:,.4f}"
            else:
                return f"{amount:,.6f}".rstrip("0").rstrip(".")

    def _get_currency_name(self, code: str) -> str:
        """Get friendly name for currency code"""
        names = {
            "USD": "United States Dollar ($)",
            "EUR": "Euro (€)",
            "JPY": "Japanese Yen (¥)",
            "GBP": "British Pound (£)",
            "CNY": "Chinese Yuan (¥)",
            "AUD": "Australian Dollar (A$)",
            "CAD": "Canadian Dollar (C$)",
            "CHF": "Swiss Franc (Fr)",
            "HKD": "Hong Kong Dollar (HK$)",
            "SGD": "Singapore Dollar (S$)",
            "NZD": "New Zealand Dollar (NZ$)",
            "SEK": "Swedish Krona (kr)",
            "KRW": "South Korean Won (₩)",
            "NOK": "Norwegian Krone (kr)",
            "INR": "Indian Rupee (₹)",
            "MXN": "Mexican Peso ($)",
            "BRL": "Brazilian Real (R$)",
            "ZAR": "South African Rand (R)",
            "TRY": "Turkish Lira (₺)",
            "DKK": "Danish Krone (kr)",
            "PLN": "Polish Zloty (zł)",
            "CZK": "Czech Koruna (Kč)",
            "ILS": "Israeli New Shekel (₪)",
            "THB": "Thai Baht (฿)",
            "MYR": "Malaysian Ringgit (RM)",
            "PHP": "Philippine Peso (₱)",
            "IDR": "Indonesian Rupiah (Rp)",
            "HUF": "Hungarian Forint (Ft)",
            "RON": "Romanian Leu (lei)",
            "BGN": "Bulgarian Lev (лв)",
            "ISK": "Icelandic Króna (kr)",
            "BTC": "Bitcoin (BTC)",
            "SOL": "Solana (SOL)",
            "ETH": "Ethereum (ETH)",
        }
        return names.get(code, code)

    async def convert_currency(
        self,
        from_currency: str,
        to_currency: Optional[str] = None,
        amount: Optional[float] = 1.0,
        __user__: dict = {},
    ) -> str:
        """
        Convert between ANY currencies - works for ALL combinations of fiat and crypto.
        This tool handles crypto-to-crypto, crypto-to-fiat, fiat-to-crypto, and fiat-to-fiat conversions.

        :param from_currency: Source currency code (e.g., USD, BTC, EUR, SOL, ETH, GBP)
        :param to_currency: Target currency code (optional, defaults to USD if not provided)
        :param amount: Amount to convert (optional, defaults to 1)
        :return: Conversion result with formatted rates

        EXAMPLES:
        - BTC to SOL: from_currency="BTC", to_currency="SOL", amount=2
        - USD to BTC: from_currency="USD", to_currency="BTC", amount=1000
        - EUR to GBP: from_currency="EUR", to_currency="GBP", amount=100
        - SOL to USD: from_currency="SOL", to_currency="USD", amount=10
        - ETH to EUR: from_currency="ETH", to_currency="EUR", amount=0.5

        IMPORTANT: This tool can convert DIRECTLY between any two currencies.
        Do NOT do manual calculations - just call this tool with the correct parameters!
        """
        try:
            # Fetch rates
            data = self._fetch_rates()
            rates = data.get("rates", {})
            base = data.get("base", "USD")
            updated = data.get("updated", "")

            # Normalize currency codes to uppercase
            from_currency = from_currency.upper().strip()
            to_currency = to_currency.upper().strip() if to_currency else base

            # Validate currencies exist
            if from_currency not in rates and from_currency != base:
                available = ", ".join(sorted(rates.keys())[:20])
                return f"❌ Currency '{from_currency}' not found. Available currencies include: {available}..."

            if to_currency not in rates and to_currency != base:
                available = ", ".join(sorted(rates.keys())[:20])
                return f"❌ Currency '{to_currency}' not found. Available currencies include: {available}..."

            # Calculate conversion
            # API uses different formats:
            # - Crypto (BTC, ETH, SOL): rates[crypto] = "1 crypto = X USD"
            # - Fiat: rates[fiat] = "1 USD = X fiat"

            crypto_currencies = ["BTC", "ETH", "SOL"]
            from_is_crypto = from_currency in crypto_currencies
            to_is_crypto = to_currency in crypto_currencies

            if from_currency == base:
                # Converting from USD
                if to_is_crypto:
                    # USD to crypto: 1 crypto = rates[crypto] USD
                    result = amount / rates[to_currency]
                else:
                    # USD to fiat: 1 USD = rates[fiat] fiat
                    result = amount * rates[to_currency]

            elif to_currency == base:
                # Converting to USD
                if from_is_crypto:
                    # Crypto to USD: 1 crypto = rates[crypto] USD
                    result = amount * rates[from_currency]
                else:
                    # Fiat to USD: 1 USD = rates[fiat] fiat
                    result = amount / rates[from_currency]

            else:
                # Converting between two non-USD currencies
                # First convert to USD, then to target
                if from_is_crypto:
                    # Crypto to USD
                    usd_value = amount * rates[from_currency]
                else:
                    # Fiat to USD
                    usd_value = amount / rates[from_currency]

                if to_is_crypto:
                    # USD to crypto
                    result = usd_value / rates[to_currency]
                else:
                    # USD to fiat
                    result = usd_value * rates[to_currency]

            # Calculate rate: always result/amount for correct display
            rate = result / amount

            # Format output
            from_name = self._get_currency_name(from_currency)
            to_name = self._get_currency_name(to_currency)
            formatted_amount = self._format_amount(amount, from_currency)
            formatted_result = self._format_amount(result, to_currency)
            formatted_rate = self._format_amount(rate, to_currency)

            # Parse update time
            update_time = ""
            if updated:
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    update_time = (
                        f"\n🕐 Updated: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                except:
                    pass

            # Build response
            response = f"💱 **Currency Conversion**\n\n"
            response += f"**{formatted_amount} {from_currency}** ({from_name})\n"
            response += f"= **{formatted_result} {to_currency}** ({to_name})\n\n"
            response += f"📊 Rate: 1 {from_currency} = {formatted_rate} {to_currency}"
            response += update_time

            return response

        except Exception as e:
            return f"❌ Error: {str(e)}"

    async def get_crypto_price(
        self, crypto: str = "BTC", currency: str = "USD", __user__: dict = {}
    ) -> str:
        """
        Get current cryptocurrency price in any currency. This is a shortcut for convert_currency.

        :param crypto: Cryptocurrency code - BTC, ETH, or SOL (default: BTC)
        :param currency: Target currency code - any fiat or crypto (default: USD)
        :return: Current crypto price with details

        EXAMPLES:
        - Bitcoin price in USD: crypto="BTC", currency="USD"
        - Ethereum price in EUR: crypto="ETH", currency="EUR"
        - Solana price in GBP: crypto="SOL", currency="GBP"

        NOTE: For conversions with amounts other than 1, use convert_currency instead.
        """
        return await self.convert_currency(
            from_currency=crypto, to_currency=currency, amount=1.0, __user__=__user__
        )

    async def list_currencies(
        self, filter_type: Optional[str] = None, __user__: dict = {}
    ) -> str:
        """
        List all available currencies.

        :param filter_type: Filter by type: 'crypto', 'fiat', or None for all
        :return: List of available currencies
        """
        try:
            data = self._fetch_rates()
            rates = data.get("rates", {})
            base = data.get("base", "USD")

            crypto = ["BTC", "ETH", "SOL"]
            all_currencies = [base] + list(rates.keys())

            if filter_type:
                filter_type = filter_type.lower()
                if filter_type == "crypto":
                    currencies = [c for c in all_currencies if c in crypto]
                    title = "Cryptocurrencies"
                elif filter_type == "fiat":
                    currencies = [c for c in all_currencies if c not in crypto]
                    title = "Fiat Currencies"
                else:
                    return f"❌ Invalid filter type. Use 'crypto', 'fiat', or leave empty for all."
            else:
                currencies = all_currencies
                title = "All Currencies"

            # Build response
            response = f"💰 **{title}** ({len(currencies)} available)\n\n"

            # Group currencies
            crypto_list = [c for c in currencies if c in crypto]
            fiat_list = [c for c in currencies if c not in crypto]

            if crypto_list:
                response += "**🪙 Cryptocurrencies:**\n"
                for code in sorted(crypto_list):
                    name = self._get_currency_name(code)
                    response += f"• {code} - {name}\n"
                response += "\n"

            if fiat_list:
                response += "**💵 Fiat Currencies:**\n"
                # Show in columns
                for i in range(0, len(fiat_list), 3):
                    row = fiat_list[i : i + 3]
                    response += "• " + ", ".join(sorted(row)) + "\n"

            return response

        except Exception as e:
            return f"❌ Error: {str(e)}"
