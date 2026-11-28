"""MUHR Buyer MCP Server: lets an AI agent hire marketplace sellers."""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server import Server  # noqa: E402
from mcp.types import TextContent, Tool  # noqa: E402

from buyer_mcp.budget import BudgetManager, wait_for_approval  # noqa: E402
from buyer_mcp.flow import BuyerFlow, FlowError  # noqa: E402
from buyer_mcp.lightning import LightningWallet  # noqa: E402
from buyer_mcp.registry_client import RegistryClient, RegistryError  # noqa: E402
from shared import schemas  # noqa: E402
from shared.constants import env_flag  # noqa: E402

# MCP speaks JSON-RPC on stdout, so logs must go to stderr.
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Server("muhr-buyer")
registry = RegistryClient()
lightning_wallet = LightningWallet()
budget_manager = BudgetManager(registry=registry)
flow = BuyerFlow(registry, lightning_wallet, budget_manager)


def _text(s: str) -> list[TextContent]:
    return [TextContent(type="text", text=s)]


def lightning_send_enabled() -> bool:
    """`lightning_send` moves the buyer's own funds to any destination, so it is off unless asked for."""
    return env_flag("MUHR_ENABLE_LIGHTNING_SEND", False)


@app.list_tools()
async def list_tools() -> list[Tool]:
    tools = _all_tools()
    return tools if lightning_send_enabled() else [t for t in tools if t.name != "lightning_send"]


def _all_tools() -> list[Tool]:
    return [
        Tool(name="wallet_status", description="Show the buyer wallet mode (REAL/DEMO), balance and remaining daily budget",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="lightning_send",
             description="Send sats via MDK to a bolt11 / lightning address / LNURL / BOLT12 (REAL mode only; counts against the daily budget)",
             inputSchema={"type": "object", "properties": {
                 "destination": {"type": "string"},
                 "amount_sats": {"type": "integer", "description": "Required unless the bolt11 carries an amount"}},
                 "required": ["destination", "amount_sats"]}),
        Tool(name="find_sellers", description="Find sellers by capability, ranked by success rate",
             inputSchema={"type": "object", "properties": {
                 "capability": {"type": "string"}, "max_price": {"type": "integer"}, "min_jobs": {"type": "integer"}},
                 "required": ["capability"]}),
        Tool(name="post_task", description="Post a task; returns task_id for send_encrypted_job",
             inputSchema={"type": "object", "properties": {
                 "capability_needed": {"type": "string"}, "budget_sats": {"type": "integer"},
                 "buyer_pubkey": {"type": "string"}, "input_schema": {"type": "object"}},
                 "required": ["capability_needed", "budget_sats", "buyer_pubkey"]}),
        Tool(name="send_encrypted_job",
             description="Hire a seller for a posted task: seal the data to the seller, pay the verified invoice, decrypt and verify the result",
             inputSchema={"type": "object", "properties": {
                 "task_id": {"type": "string"}, "seller_id": {"type": "string"}, "job_data": {"type": "string"}},
                 "required": ["task_id", "seller_id", "job_data"]}),
        Tool(name="request_human_approval", description="Ask a human operator to approve a spend; waits up to 5 minutes",
             inputSchema={"type": "object", "properties": {
                 "reason": {"type": "string"}, "amount_sats": {"type": "integer"}, "task_description": {"type": "string"}},
                 "required": ["reason", "amount_sats", "task_description"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        handler = {
            "wallet_status": wallet_status_impl, "lightning_send": lightning_send_impl,
            "find_sellers": find_sellers_impl, "post_task": post_task_impl,
            "send_encrypted_job": send_encrypted_job_impl, "request_human_approval": request_human_approval_impl,
        }.get(name)
        if handler is None or (name == "lightning_send" and not lightning_send_enabled()):
            return _text(f"Unknown tool: {name}")
        return await handler(arguments or {})
    except (FlowError, RegistryError) as e:
        return _text(f"Error: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("Tool %s failed", name)
        return _text(f"Error: {e.__class__.__name__}: {e}")


async def wallet_status_impl(_args: dict) -> list[TextContent]:
    s = await lightning_wallet.wallet_status()
    lines = [f"Wallet mode: {s.get('mode')}", f"Remaining daily budget: {budget_manager.remaining()} sats"]
    if s.get("balance_sats") is not None:
        lines.append(f"Balance: {s['balance_sats']} sats")
    if s.get("detail"):
        lines.append(f"Detail: {s['detail']}")
    return _text("\n".join(lines))


async def lightning_send_impl(args: dict) -> list[TextContent]:
    dest = str(args.get("destination") or "").strip()
    amount = int(args["amount_sats"])
    await budget_manager.reserve(amount, description=f"lightning_send to {dest[:40]}")
    r = await lightning_wallet.send_lightning(dest, amount)
    if r.get("success"):
        await budget_manager.commit(amount)
        return _text(f"OK: {r.get('data')!r}")
    await budget_manager.release(amount)
    return _text(f"Error: {r.get('error')!r}")


async def find_sellers_impl(args: dict) -> list[TextContent]:
    resp = await registry.get_sellers(capability=args["capability"], max_price=args.get("max_price"),
                                      min_jobs=args.get("min_jobs"))
    sellers = resp.sellers[:5]
    if not sellers:
        return _text(f"No sellers found for capability: {args['capability']}")
    out = [f"Found {len(sellers)} seller(s) for {args['capability']}:"]
    for i, s in enumerate(sellers, 1):
        out.append(f"{i}. {s.seller_id}  price {s.price_sats_per_unit} sats {s.unit_definition}  "
                   f"success {s.reputation_score:.0f}% ({s.jobs_completed} ok / {s.jobs_failed} failed)  "
                   f"stake {s.stake_sats}  {s.endpoint_url}")
    return _text("\n".join(out))


async def post_task_impl(args: dict) -> list[TextContent]:
    resp = await flow.post_task(capability=args["capability_needed"], budget_sats=int(args["budget_sats"]),
                                buyer_pubkey=args["buyer_pubkey"], input_schema=args.get("input_schema") or {})
    return _text(f"Task posted: {resp.task_id}\nExpires: {resp.expires_at}\n"
                 f"Matched sellers: {', '.join(resp.matched_sellers) or 'none'}")


async def send_encrypted_job_impl(args: dict) -> list[TextContent]:
    text = str(args["job_data"])
    r = await flow.hire(args["task_id"], args["seller_id"], text)
    return _text(
        "Job completed and verified.\n\n"
        f"Job ID: {r.job_id}\nSeller: {r.seller_id}\nPaid: {r.amount_sats} sats ({r.mode}, verified by {r.payment_verified_by})\n"
        f"Payment hash: {r.payment_hash}\nResult hash: {r.result_hash}\n\nResult:\n{r.result_text}\n")


async def request_human_approval_impl(args: dict) -> list[TextContent]:
    req = schemas.ApprovalRequest(request_id=f"appr_{uuid.uuid4().hex[:12]}", reason=args["reason"],
                                  amount_sats=int(args["amount_sats"]), task_description=args["task_description"])
    await registry.request_approval(req)
    approved = await wait_for_approval(registry, req.request_id)
    status = (await registry.get_approval_status(req.request_id)).status
    return _text(f"Approval {req.request_id}: {'GRANTED' if approved else status.upper() if status != 'pending' else 'TIMED OUT'}")


async def main() -> None:
    from mcp.server.stdio import stdio_server

    logger.info("Starting MUHR Buyer MCP Server (registry=%s)", registry.base_url)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
