import pytest
from unittest.mock import MagicMock, patch
from atheriz.commands.loggedin.delete import DeleteCommand

@pytest.fixture
def mock_caller():
    caller = MagicMock()
    caller.location = MagicMock()
    caller.location.access.return_value = True
    caller.location.search.return_value = []
    caller.search.return_value = []
    caller.is_builder = True
    return caller

@pytest.fixture
def delete_cmd():
    cmd = DeleteCommand()
    cmd.parser = MagicMock()
    return cmd

def test_delete_here(mock_caller, delete_cmd):
    args = MagicMock()
    args.target = ["here"]
    args.recursive = False
    mock_caller.location.delete.return_value = 1
    
    with patch("atheriz.commands.loggedin.delete.remove_object"):
        delete_cmd.run(mock_caller, args)
    
    # Verify that it tried to delete the location
    assert mock_caller.location.delete.called
    mock_caller.location.delete.assert_called_once_with(mock_caller, False)

def test_delete_coord(mock_caller, delete_cmd):
    args = MagicMock()
    args.target = ["(test,0,0,0)"]
    args.recursive = True
    
    mock_node = MagicMock()
    mock_node.delete.return_value = 1
    
    with patch("atheriz.commands.loggedin.delete.get_node_handler") as mock_get_nh:
        mock_nh = mock_get_nh.return_value
        mock_nh.get_node.return_value = mock_node
        
        with patch("atheriz.commands.loggedin.delete.remove_object"):
            delete_cmd.run(mock_caller, args)
    
    mock_nh.get_node.assert_called_with(("test", 0, 0, 0))
    assert mock_node.delete.called

def test_delete_coord_no_parens(mock_caller, delete_cmd):
    args = MagicMock()
    args.target = ["test,0,0,0"]
    args.recursive = False
    
    mock_node = MagicMock()
    mock_node.delete.return_value = 1
    
    with patch("atheriz.commands.loggedin.delete.get_node_handler") as mock_get_nh:
        mock_nh = mock_get_nh.return_value
        mock_nh.get_node.return_value = mock_node
        
        with patch("atheriz.commands.loggedin.delete.remove_object"):
            delete_cmd.run(mock_caller, args)
    
    mock_nh.get_node.assert_called_with(("test", 0, 0, 0))
    assert mock_node.delete.called

def test_delete_search_fallback(mock_caller, delete_cmd):
    args = MagicMock()
    args.target = ["my_target"]
    args.recursive = False
    
    target_obj = MagicMock()
    target_obj.delete.return_value = 1
    mock_caller.search.return_value = [target_obj]
    
    with patch("atheriz.commands.loggedin.delete.remove_object"):
        delete_cmd.run(mock_caller, args)
    
    mock_caller.search.assert_called_with("my_target")
    assert target_obj.delete.called
    target_obj.delete.assert_called_once_with(mock_caller, False)
