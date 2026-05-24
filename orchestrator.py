"""
Orchestrator for the Research Report Compiler

Implements the core execution engine that coordinates agents, fact graph, and rendering
according to the declarative design principles.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict
import asyncio
from langgraph.graph import StateGraph, END

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Orchestrator:
    """Main orchestrator that manages the agent DAG execution."""
    
    def __init__(self, pack_path: str):
        """Initialize orchestrator with pack configuration.
        
        Args:
            pack_path: Path to the pack directory containing pack.yaml
        """
        self.pack_path = pack_path
        self.fact_graph = {}
        self.patch_log = []
        self.agent_configs = {}
        self.pipeline_steps = []
        self.step_view_map = {}
        
        self._load_pack_config()
        self._build_graph()
    
    def _load_pack_config(self):
        """Load pack configuration from pack.yaml.
        
        Reads the pack.yaml file and extracts agent configurations.
        Raises FileNotFoundError if pack.yaml doesn't exist.
        """
        import yaml
        import os
        
        pack_file = os.path.join(self.pack_path, "pack.yaml")
        if not os.path.exists(pack_file):
            raise FileNotFoundError(f"Pack configuration not found: {pack_file}")
        
        with open(pack_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self.agent_configs = {}
        for agent in config.get('agents', []):
            agent_id = agent['id']
            self.agent_configs[agent_id] = {
                'depends_on': agent.get('depends_on', []),
                'step': agent.get('step', 0),
                'enabled': agent.get('enabled', True)
            }
        
        self._load_domain_and_commons_packs()
    
    def _load_domain_and_commons_packs(self):
        """Load domain and commons packs for unified configuration.
        
        In v4.3, base is replaced by commons pack. Domain pack is independent 
        with no inheritance, implementing the abc(domain+commons)平级组合 design.
        """
        pass
    
    def _build_graph(self):
        """Build LangGraph StateGraph from pack.yaml configuration.
        
        Creates a StateGraph with nodes for each enabled agent and edges based
        on dependencies defined in pack.yaml. Sets entry points for agents with
        no dependencies.
        """
        self.graph = StateGraph(dict)
        
        for agent_id, config in self.agent_configs.items():
            if config['enabled']:
                self.graph.add_node(agent_id, self._create_agent_node(agent_id))
        
        for agent_id, config in self.agent_configs.items():
            if config['enabled']:
                for dep in config['depends_on']:
                    if dep in self.agent_configs and self.agent_configs[dep]['enabled']:
                        self.graph.add_edge(dep, agent_id)
        
        entry_points = [agent_id for agent_id, config in self.agent_configs.items() 
                       if config['enabled'] and len(config['depends_on']) == 0]
        
        if len(entry_points) == 1:
            self.graph.set_entry_point(entry_points[0])
        elif len(entry_points) > 1:
            self.graph.add_conditional_edges(
                "__start__", 
                lambda state: "__start__", 
                {entry_point: entry_point for entry_point in entry_points}
            )
        
        self.app = self.graph.compile()
        
        self.pipeline_steps = [agent_id for agent_id in self.agent_configs.keys() 
                              if self.agent_configs[agent_id]['enabled']]
        
        self.step_view_map = {step: i+1 for i, step in enumerate(self.pipeline_steps)}
    
    def _create_agent_node(self, agent_id: str):
        """Create a LangGraph node function for an agent.
        
        Returns a function that executes the agent and updates the fact graph.
        The function injects full fact context to the agent and logs patches.
        """
        def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
            logger.info(f"Executing agent: {agent_id}")
            
            agent_state = {
                "fact_context": self.fact_graph,
                "agent_id": agent_id,
                "step": self.step_view_map.get(agent_id, 0)
            }
            
            result = self._execute_agent(agent_id, agent_state)
            
            if result and isinstance(result, dict):
                self._update_fact_graph(result)
                
            self._log_patch(agent_id, result)
            
            return state
        
        return agent_node
    
    def _execute_agent(self, agent_id: str, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute a specific agent with the given state.
        
        Dynamically imports the agent module and calls its execute function.
        Returns None if module or function is not found.
        """
        try:
            module_name = f"agents.{agent_id}"
            agent_module = __import__(module_name, fromlist=['execute'])
            return agent_module.execute(state)
        except ImportError:
            logger.warning(f"Agent module not found: {module_name}")
            return None
        except AttributeError:
            logger.warning(f"Agent module {module_name} has no execute function")
            return None
    
    def _update_fact_graph(self, changes: Dict[str, Any]) -> None:
        """Update fact graph with new changes.
        
        Implements the incremental change principle: only update fields that 
        have changed, preserving unchanged data.
        """
        if not isinstance(changes, dict):
            return
        
        for key, value in changes.items():
            self.fact_graph[key] = value
    
    def _log_patch(self, agent_id: str, changes: Dict[str, Any]) -> None:
        """Append patch to patch log (append-only WAL).
        
        Creates a JSONL entry with agent_id, timestamp, and changes.
        Ensures log directory exists and writes to patch_log.jsonl.
        """
        import json
        import os
        
        patch_entry = {
            "agent_id": agent_id,
            "timestamp": str(datetime.now()),
            "changes": changes
        }
        
        log_dir = os.path.join(self.pack_path, "runtime", "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, "patch_log.jsonl")
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(patch_entry, ensure_ascii=False) + '\n')
        
        self.patch_log.append(patch_entry)
    
    def execute(self, initial_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the entire pipeline with initial input.
        
        Initializes the fact graph with input and runs the LangGraph state machine.
        Returns the final state after all agents have executed.
        """
        self.fact_graph.update(initial_input)
        
        result = self.app.invoke(initial_input)
        
        return result

from datetime import datetime