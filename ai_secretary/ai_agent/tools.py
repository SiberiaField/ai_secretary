import inspect
from typing import Any, Callable, Optional, Dict, Type, get_origin, get_args, Annotated, Union

from pydantic import BaseModel, Field, TypeAdapter, create_model, PrivateAttr
from pydantic.json_schema import JsonSchemaValue
from pydantic.fields import FieldInfo
from typing import get_type_hints, List


class Tool(BaseModel):
    name: str
    description: str
    func: Callable[..., str]
    parameters_json_schema: JsonSchemaValue
    is_async: bool = False
    
    _params_adapter: Optional[TypeAdapter] = PrivateAttr(default=None)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_function(
        cls,
        func: Optional[Callable[..., str]] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Union["Tool", Callable[[Callable[..., str]], "Tool"]]:
        """
        Создает Tool из функции с автоматической генерацией JSON Schema.
        Может использоваться как обычный метод, так и как декоратор.
        """
        def decorator(f: Callable[..., str]) -> "Tool":
            tool_name = name or f.__name__
            tool_description = description or (f.__doc__ or "No description provided.").strip().split('\n')[0]
            is_async = inspect.iscoroutinefunction(f)
            
            sig = inspect.signature(f)
            params = sig.parameters
            
            params_model = cls._create_parameters_model_with_annotated(f, params)
            
            if params_model:
                adapter = TypeAdapter(params_model)
                parameters_schema = adapter.json_schema()
            else:
                parameters_schema = {"type": "object", "properties": {}, "required": []}
                adapter = None
            
            return cls(
                name=tool_name,
                description=tool_description,
                func=f,
                parameters_json_schema=parameters_schema,
                is_async=is_async,
                _params_adapter=adapter,
            )

        if func is not None:
            return decorator(func)
        
        return decorator
    
    @classmethod
    def _create_parameters_model_with_annotated(
        cls, 
        func: Callable[..., str], 
        params: Dict[str, inspect.Parameter]
    ) -> Optional[Type[BaseModel]]:
        """
        Создает Pydantic модель из параметров функции.
        """
        if not params:
            return None
        
        type_hints = get_type_hints(func, include_extras=True)
        
        fields = {}
        for param_name, param in params.items():
            if param_name in ("self", "cls", "context", "ctx", "run_context"):
                continue
            
            param_type = type_hints.get(param_name, param.annotation)
            
            if param_type == inspect.Parameter.empty:
                param_type = str

            default_value = param.default
            is_required = default_value == inspect.Parameter.empty
            
            description = cls._extract_description_from_annotated(param_type)
            
            if description:
                field_info = Field(
                    default=... if is_required else default_value,
                    description=description,
                )
            else:
                field_info = Field(
                    default=... if is_required else default_value,
                    description=f"Parameter '{param_name}'",
                )

            base_type = cls._extract_base_type_from_annotated(param_type)
            
            fields[param_name] = (base_type, field_info)
        
        if not fields:
            return None
        
        model_name = f"Params_{func.__name__}_{id(params)}"
        return create_model(model_name, **fields)
    
    @classmethod
    def _extract_description_from_annotated(cls, typ: Any) -> Optional[str]:
        """
        Извлекает описание из Annotated типа, если оно там есть.
        """
        if get_origin(typ) is not Annotated:
            return None
        
        args = get_args(typ)
        if len(args) < 2:
            return None
        
        for metadata in args[1:]:
            if isinstance(metadata, FieldInfo):
                return metadata.description
        
        return None
    
    @classmethod
    def _extract_base_type_from_annotated(cls, typ: Any) -> Any:
        """
        Извлекает базовый тип из Annotated.
        Для Annotated[str, Field(...)] возвращает str.
        Для обычных типов возвращает сам тип.
        """
        if get_origin(typ) is not Annotated:
            return typ

        args = get_args(typ)
        if args:
            return args[0]
        
        return typ
    
    def to_llm_definition(self) -> Dict:
        return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters_json_schema,
                }
            }
    

class ToolSet:
    def __init__(self, name: str, description: str, tools: List[Tool] | None):
        self.name = name
        self.description = description
        self.tools = {tool.name: tool for tool in tools} if tools is not None else None
        
    def add_tool(self, tool: Tool):
        """Добавляет инструмент в набор. Проверяет уникальность имен."""
        if tool.name in self.tools:
            raise ValueError(f"Tool with name '{tool.name}' already exists in this ToolSet.")
        self.tools[tool.name] = tool
    
    def to_llm_definition(self) -> List[Dict]:
        """Форматирует набор инструментов в список словарей для API LLM."""
        return [tool.to_llm_definition() for tool in self.tools.values()]
