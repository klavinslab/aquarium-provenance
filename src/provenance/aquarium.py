"""
Aquarium provenance classes derived using pydent models.
See TraceFactory.create_from to load.

Loosely based on provenance ontology, which includes activities, agents,
and entities.

Note that I punted on properly modeling which kinds of entities in Aquarium.
An Item has a sample and object_type;
a collection has no sample but has an object_type; and
a part of a collection has a sample but no object_type.
"""
import abc
import json
import sys


class AttributesMixin(abc.ABC):
    """
    Defines an abstract class to serve as a mixin for classes with objects that
    should carry attributes.

    In Aquarium, only a Plan, Item and Operation may carry data associations
    from which these are populated, so only apply these to the corresponding
    classes.
    """

    @abc.abstractmethod
    def __init__(self):
        self.attributes = dict()
        super().__init__()

    def add_attribute(self, attribute):
        for key, value in attribute.items():
            if value:
                self.attributes[key] = value

    def as_dict(self):
        attr_dict = dict()
        if self.attributes:
            attr_dict['attributes'] = self.attributes
        return attr_dict


class AbstractEntity(abc.ABC):
    """
    Defines an abstract class with the properties of an entity from the
    perspective of provenance.
    Specifically, has the generating operation, and a list of source entities.
    """

    @abc.abstractmethod
    def __init__(self):
        self.generator = None
        self.sources = list()
        super().__init__()

    def add_generator(self, operation):
        self.generator = operation

    def add_source(self, entity):
        self.sources.append(entity)

    def get_source_ids(self):
        return [item_entity.item_id for item_entity in self.sources]

    def as_dict(self):
        entity_dict = dict()
        if self.generator:
            entity_dict['generated_by'] = self.generator.operation_id
        source_ids = self.get_source_ids()
        if source_ids:
            entity_dict['sources'] = source_ids
        return entity_dict


class AbstractItemEntity(AbstractEntity, AttributesMixin):
    """
    Defines an abstract entity representing an item.
    """

    @abc.abstractmethod
    def __init__(self, *, item_id, item_type):
        self.item_id = str(item_id)
        self.item_type = item_type
        super().__init__()

    def as_dict(self):
        item_dict = dict()
        item_dict['item_id'] = self.item_id
        item_dict['type'] = self.item_type
        entity_dict = AbstractEntity.as_dict(self)
        attr_dict = AttributesMixin.as_dict(self)
        return {**item_dict, **{**entity_dict, **attr_dict}}


class ItemEntity(AbstractItemEntity):
    """
    Defines an entity class for an Aquarium Item object.
    """

    def __init__(self, *, item):
        self.item = item
        self.sample = item.sample
        self.object_type = item.object_type
        super().__init__(item_id=item.id, item_type='item')

    def apply(self, visitor):
        visitor.visit_item(self)

    def as_dict(self):
        item_dict = super().as_dict()
        sample_dict = dict()
        sample_dict['sample_id'] = str(self.sample.id)
        sample_dict['sample_name'] = self.sample.name
        item_dict['sample'] = sample_dict
        type_dict = dict()
        type_dict['object_type_id'] = str(self.object_type.id)
        type_dict['object_type_name'] = self.object_type.name
        item_dict['object_type'] = type_dict
        return item_dict


class CollectionEntity(AbstractItemEntity):
    """
    Defines an entity class for an Aquarium Collection object.
    """

    def __init__(self, collection):
        self.object_type = collection.object_type
        self.collection = collection
        super().__init__(item_id=collection.id, item_type='collection')

    def apply(self, visitor):
        visitor.visit_collection(self)

    def as_dict(self):
        item_dict = super().as_dict()
        type_dict = dict()
        type_dict['object_type_id'] = str(self.object_type.id)
        type_dict['object_type_name'] = self.object_type.name
        item_dict['object_type'] = type_dict
        return item_dict


class FileEntity(AbstractEntity):
    """
    Defines an entity class for a file
    (corresponds to an Aquarium Upload object).
    """

    def __init__(self, *, upload):
        self.file_id = str(upload.id)
        self.name = upload.name
        self.size = upload.size
        self.upload = upload
        super().__init__()

    def apply(self, visitor):
        visitor.visit_file(self)

    def as_dict(self):
        file_dict = super().as_dict()
        file_dict['file_id'] = self.file_id
        file_dict['filename'] = self.name
        file_dict['size'] = self.size
        return file_dict


class OperationActivity(AttributesMixin):

    def __init__(self, operation):
        self.operation_id = str(operation.id)
        self.operation_type = operation.operation_type
        self.operation = operation
        self.inputs = list()

    def add_input(self, input):
        self.inputs.append(input)

    def apply(self, visitor):
        visitor.visit_operation(self)

    def as_dict(self):
        op_dict = dict()
        op_dict['operation_id'] = self.operation_id
        op_type = dict()
        op_type['operation_type_id'] = str(self.operation_type.id)
        op_type['category'] = self.operation_type.category
        op_type['name'] = self.operation_type.name
        op_dict['operation_type'] = op_type
        op_dict['inputs'] = [input.as_dict() for input in self.inputs]
        return op_dict


class OperationArgument(abc.ABC):
    """
    Models an argument to an operation, which can be either a 
    (though use it to capture output during trace conversion)
    """

    @abc.abstractmethod
    def __init__(self, *, name, field_value_id):
        self.name = name
        self.field_value_id = str(field_value_id)

    @staticmethod
    def create_from(field_value):
        if field_value.child_item_id is None:
            return OperationParameter(
                name=field_value.name,
                field_value_id=field_value.id,
                value=field_value.value)
        else:
            return OperationInput(
                name=field_value.name,
                field_value_id=field_value.id,
                item_id=field_value.child_item_id
            )

    def is_item(self):
        """
        Return true if this argument is an input item or collection, and
        false, otherwise.
        """
        return False

    def as_dict(self):
        arg_dict = dict()
        arg_dict['name'] = self.name
        arg_dict['field_value_id'] = self.field_value_id
        return arg_dict


class OperationParameter(OperationArgument):

    def __init__(self, *, name, field_value_id, value):
        self.value = value
        super().__init__(name=name, field_value_id=field_value_id)

    def as_dict(self):
        arg_dict = super().as_dict()
        arg_dict['value'] = self.value
        return arg_dict


class OperationInput(OperationArgument):

    def __init__(self, *, name, field_value_id, item_id):
        self.item_id = str(item_id)
        super().__init__(name=name, field_value_id=field_value_id)

    def is_item(self):
        return True

    def as_dict(self):
        arg_dict = super().as_dict()
        arg_dict['item_id'] = self.item_id
        return arg_dict


class PartEntity(AbstractItemEntity):

    def __init__(self, *, part_id, sample, collection):
        self.sample = sample
        self.collection = collection
        super().__init__(item_id=part_id, item_type='part')

    def get_sample(self):
        return self.sample

    def apply(self, visitor):
        visitor.visit_part(self)

    def as_dict(self):
        item_dict = super().as_dict()
        item_dict['part_of'] = self.collection.item_id
        sample_dict = dict()
        sample_dict['sample_id'] = str(self.sample.id)
        sample_dict['sample_name'] = self.sample.name
        item_dict['sample'] = sample_dict
        return item_dict


class PlanTrace(AttributesMixin):

    def __init__(self, *, plan_id: int, name: str):
        self.plan_id = str(plan_id)
        self.plan_name = name
        self.operations = dict()
        self.items = dict()
        self.files = dict()
        super().__init__()

    def add_file(self, file_entity):
        self.files[file_entity.file_id] = file_entity

    def add_item(self, item_entity):
        self.items[item_entity.item_id] = item_entity

    def add_operation(self, operation):
        self.operations[operation.operation_id] = operation

    def has_item(self, item_id):
        return bool(item_id) and str(item_id) in self.items

    def has_file(self, file_id):
        return bool(file_id) and str(file_id) in self.files

    def get_item(self, item_id):
        return self.items[str(item_id)]

    def get_file(self, file_id):
        return self.files[str(file_id)]

    def apply(self, visitor):
        visitor.visit_trace(self)
        for _, operation in self.operations.items():
            operation.apply(visitor)
        for _, item in self.items.items():
            item.apply(visitor)
        for _, file in self.files.items():
            file.apply(visitor)

    def as_dict(self):
        trace_dict = dict()
        trace_dict['plan_id'] = self.plan_id
        trace_dict['plan_name'] = self.plan_name
        trace_dict['operations'] = [op.as_dict()
                                    for _, op in self.operations.items()]
        trace_dict['items'] = [item.as_dict()
                               for _, item in self.items.items()]
        trace_dict['files'] = [file.as_dict()
                               for _, file in self.files.items()]
        super_dict = super().as_dict()
        return {**trace_dict, **super_dict}


class TraceFactory:
    """
    Defines a factory object to create a PlanTrace from a pydent.model.Plan.
    """

    def __init__(self, *, session, trace):
        self.trace = trace
        self.session = session

    @staticmethod
    def create_from(*, session, plan):
        """
        Creates a PlanTrace for the plan from the Aquarium session.
        """
        factory = TraceFactory(
            session=session,
            trace=PlanTrace(plan_id=plan.id, name=plan.name)
        )

        # do associations first so that files are found
        for association in plan.data_associations:
            if association.upload:
                factory._get_file(upload_id=association.upload.id)
            elif association.object:
                factory.trace.add_attribute(association.object)

        for operation in plan.operations:
            factory._create_operation(operation)

        return factory.trace

    def _add_item_entity(self, *, entity, generator):
        if generator:
            entity.add_generator(generator)
        self.trace.add_item(entity)

    def _add_file_entity(self, *, entity, source):
        if source:
            entity.add_source(source)
        self.trace.add_file(entity)

    def _create_operation(self, operation):
        """
        Creates an OperationActivity object from the pydent.model.Operation
        object.
        """
        op_activity = OperationActivity(operation)
        self.trace.add_operation(op_activity)

        for field_value in operation.field_values:
            arg = OperationArgument.create_from(field_value)
            if is_input(field_value):
                op_activity.add_input(arg)

            if arg.is_item():
                if self.trace.has_item(arg.item_id):
                    if is_output(field_value):
                        item = self.trace.get_item(arg.item_id)
                        item.add_generator(op_activity)
                else:
                    if is_input(field_value):
                        self._create_items(
                            item_id=arg.item_id
                        )
                    else:
                        self._create_items(
                            item_id=arg.item_id,
                            generator=op_activity
                        )

    def _create_items(self, *, item_id, generator=None):
        item_obj = self.session.Item.find(item_id)
        if is_collection(item_obj):
            self._create_collection_entity(item_id, generator)
        else:
            self._create_item_entity(item_obj, generator)

    def _create_collection_entity(self, item_id, generator):
        item_obj = self.session.Collection.find(item_id)
        item_entity = CollectionEntity(collection=item_obj)
        self._add_item_entity(entity=item_entity, generator=generator)

        upload_matrix = None
        routing_matrix = None
        if item_obj.data_associations:
            for association in item_obj.data_associations:
                if association.upload:
                    self._get_file(
                        upload_id=association.upload.id,
                        source=item_entity
                    )
                elif association.object:
                    if is_upload_matrix(association):
                        upload_matrix = get_upload_matrix(association.object)
                    elif is_routing_matrix(association):
                        routing_matrix = get_routing_matrix(association.object)
                    else:
                        item_entity.add_attribute(association.object)

        self._create_parts(entity=item_entity,
                           generator=generator,
                           upload_matrix=upload_matrix,
                           routing_matrix=routing_matrix
                           )

    def _create_item_entity(self, item_obj, generator):
        item_entity = ItemEntity(item=item_obj)
        self._add_item_entity(entity=item_entity, generator=generator)
        if item_obj.data_associations:
            for association in item_obj.data_associations:
                if association.upload:
                    self._get_file(
                        upload_id=association.upload.id,
                        source=item_entity
                    )
                elif association.object:
                    item_entity.add_attribute(association.object)

    # TODO: this is for 96 well plates, make work for general collections
    def _create_parts(self, *,
                      entity, generator, upload_matrix, routing_matrix):
        collection = entity.collection
        item_id = entity.item_id
        for i in range(len(collection.matrix)):
            row = collection.matrix[i]
            for j in range(len(row)):
                if row[j] and not row[j] < 0:
                    part_id = str(item_id) + '/' + chr(ord('A')+i) + str(j+1)
                    sample = self.session.Sample.find(row[j])
                    if sample:
                        part_entity = PartEntity(
                            part_id=part_id,
                            sample=sample,
                            collection=entity
                        )
                        self._add_item_entity(
                            entity=part_entity,
                            generator=generator
                        )

                        # Add part as source to file
                        if upload_matrix:
                            upload_id = upload_matrix[i][j]
                            self._get_file(
                                upload_id=upload_id,
                                source=part_entity
                            )
                        # Deal with routing
                        if routing_matrix:
                            entry = routing_matrix[i][j]
                            if entry:
                                source_id = entry['source']
                                if not self.trace.has_item(source_id):
                                    print("no item for {}".format(source_id),
                                          file=sys.stderr)
                                else:
                                    item_entity = self.trace.get_item(
                                        source_id)
                                    part_entity.add_source(item_entity)
                                    
                                if 'attributes' in entry:
                                    attributes = entry['attributes']
                                    part_entity.add_attribute(attributes)

    def _get_file(self, *, upload_id, source=None):
        """
        Returns the file entity for an upload associated with a plan.
        If the entity is not currently in the trace, creates it.
        """
        if self.trace.has_file(upload_id):
            if source:
                file_entity = self.trace.get_file(upload_id)
                file_entity.add_source(source)
        else:
            file_entity = FileEntity(
                upload=self._get_upload(upload_id)
            )
            self._add_file_entity(entity=file_entity, source=source)

    def _get_upload(self, upload_id):
        return self.session.Upload.where(
            {"id": upload_id},
            {"methods": ["size", "name"]}
        )[0]


def is_item_field_value(field_value):
    return bool(field_value.child_item_id)


def is_input(field_value):
    return field_value.role == 'input'


def is_output(field_value):
    return field_value.role == 'output'


def is_collection(item_obj):
    return not bool(item_obj.sample)


def is_upload_matrix(association):
    return association.key == 'SAMPLE_UPLOADs'


def get_upload_matrix(association_object):
    return association_object['SAMPLE_UPLOADs']['upload_matrix']


def is_routing_matrix(association):
    return association.key == 'routing_matrix'


def get_routing_matrix(association_object):
    return association_object['routing_matrix']['rows']
