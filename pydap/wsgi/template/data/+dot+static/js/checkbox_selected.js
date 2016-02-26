$(function()
{

  $("#submit").click(function(event)
  {
    var checked = false
    var inputs = document.getElementById('tabs').getElementsByTagName('INPUT');

    for(var i = 0; i < inputs.length; i++) {
      if (inputs[i].type.toUpperCase()=='CHECKBOX') {
        if (inputs[i].checked) {
          checked = true
        }
      }
    }

    if (!checked) {
      alert("Select at least one variable.");
      event.preventDefault(); //stop form submission
    }

  });

});
